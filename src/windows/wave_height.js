// Stretch Traktor's parallel waveforms to the height of their layout slot.
//
// The parallel lane forms (DeckWaveDisplayForm, form IDs 885-888) take their
// height from the layout XML, but the WaveformControl inside them keeps the
// geometry of the compiled-in form definition, 87 px tall. This script resizes
// it to the form's height minus Traktor's own 4 px margin. Its horizontal
// extent is left alone so the playhead stays where Traktor puts it; the custom
// QML panel overlays the lane's left edge, after Traktor's deck letter, and
// is placed by this script too (see syncWindows). Traktor's own stem
// controls are hidden, always (see hideStems).
//
// Field offsets were found on Traktor Pro 4.5.0; the vtable is resolved from
// RTTI at runtime so it survives relinking, but the offsets may not.

const FORM_ID = 0x24;           // int: form ID (885 + deck index for parallel lanes)
const FORM_HEIGHT = 0x4c;       // int: form height from the layout
const FORM_CONTROL = 0x330;     // WaveformControl*
const CONTROL_BOTTOM = 0x54;    // NGL control rect: left, top, right, bottom at 0x48
const MARGIN = 4;
const PARALLEL_IDS = [885, 886, 887, 888];
// The lane's position is not in the form but in the control hosting it in
// TraktorMainForm (LesserRestrictedSubFormControl): the form points to that
// control's subobject at +0xc8, and its rect (left, top, right, bottom) is in
// main window coordinates. Lanes move down when Traktor shows the global
// section above them on a tall enough window.
const FORM_HOST = 0x98;
const HOST_SUBOBJECT = 0xc8;
const HOST_RECT = 0x48;
const HOST_VISIBLE = 0x94;      // u8: 0 while the lanes are hidden (views other than Parallel)

const module = Process.getModuleByName('Traktor Pro 4.exe');

function pattern(p) {
  const bytes = [];
  let v = p;
  for (let i = 0; i < 8; i++) {
    bytes.push(('0' + v.and(0xff).toString(16)).slice(-2));
    v = v.shr(8);
  }
  return bytes.join(' ');
}

function hex32(n) {
  return [0, 8, 16, 24].map(s => ('0' + ((n >>> s) & 0xff).toString(16)).slice(-2)).join(' ');
}

// MSVC x64 RTTI: the CompleteObjectLocator holds the TypeDescriptor's RVA
// after signature=1 and offset=0, and the vtable follows a pointer to it.
function resolveVtable(name) {
  const decorated = '.?AV' + name + '@@';
  const hexName = Array.from(decorated).map(c => c.charCodeAt(0).toString(16)).join(' ') + ' 00';
  const [hit] = Memory.scanSync(module.base, module.size, hexName);
  if (!hit) throw new Error('RTTI not found for ' + name);
  const tdRva = hit.address.sub(0x10).sub(module.base).toUInt32();
  for (const col of Memory.scanSync(module.base, module.size, hex32(tdRva))) {
    const locator = col.address.sub(12);
    if (locator.readU32() !== 1 || locator.add(4).readU32() !== 0) continue;
    const [ref] = Memory.scanSync(module.base, module.size, pattern(locator));
    if (ref) return ref.address.add(8);
  }
  throw new Error('vtable not found for ' + name);
}

const formVtable = resolveVtable('DeckWaveDisplayForm');

// Lane waveforms are drawn from a ring buffer of audio around the playhead;
// outside it Traktor falls back to the blurry overview stripe. Its size in
// samples is chosen per stream type with `mov r12d, imm32`; for lane
// waveforms that is 2^21 (about 47 s at 44.1 kHz). Each entry costs 8 bytes,
// so 2^21 is 16 MB per buffer. WAVE_BUFFER_LOG2 is set by wave_height.py;
// 0 leaves Traktor's size alone. Buffers created after the patch (on the
// next track load) use the new size.
const WAVE_BUFFER_LOG2 = 0;
const WAVE_BUFFER_INSN = 0x676c35;  // RVA of the instruction, Traktor 4.5.1 (4.5.0: 0x676c25)
const WAVE_BUFFER_ORIGINAL = [0x41, 0xbc, 0x00, 0x00, 0x20, 0x00];

function patchWaveBuffer() {
  if (!WAVE_BUFFER_LOG2) return null;
  const insn = module.base.add(WAVE_BUFFER_INSN);
  const bytes = Array.from(new Uint8Array(insn.readByteArray(6)));
  if (bytes.some((b, i) => b !== WAVE_BUFFER_ORIGINAL[i])) {
    return 'wave buffer: unexpected bytes ' + bytes.map(b => b.toString(16)).join(' ') + ', not patched';
  }
  Memory.patchCode(insn.add(2), 4, code => code.writeU32(2 ** WAVE_BUFFER_LOG2));
  return 'wave buffer: 2^' + WAVE_BUFFER_LOG2 + ' samples';
}

const FORM_STEMS = 0x638;       // DeckWaveDisplayForm::StemControls*
// A method Traktor calls continuously on the UI thread for every control,
// lane forms included (on their subobject at UI_TICK_SUBOBJECT). All work
// happens inside it: on the thread that owns the layout, and without
// periodic memory scans, which would block that thread while the script
// engine is busy.
const UI_TICK_SLOT = 21;
const UI_TICK_SUBOBJECT = 0x18;

let laneHeight = 0;
let laneHost = null;

function isLaneForm(form) {
  try {
    return form.readPointer().equals(formVtable) && PARALLEL_IDS.includes(form.add(FORM_ID).readS32());
  } catch (e) {
    return false;
  }
}

function stretchWave(form) {
  const wave = form.add(FORM_CONTROL).readPointer();
  if (wave.isNull()) return;
  const height = form.add(FORM_HEIGHT).readS32();
  if (form.add(FORM_ID).readS32() === PARALLEL_IDS[0]) {
    // Every panel is placed from lane A, as on macOS.
    laneHeight = height;
    const host = form.add(FORM_HOST).readPointer();
    laneHost = host.isNull() ? null : host.sub(HOST_SUBOBJECT);
  }
  const bottom = height - MARGIN;
  if (bottom > 0 && wave.add(CONTROL_BOTTOM).readS32() !== bottom) {
    wave.add(CONTROL_BOTTOM).writeS32(bottom);
  }
}

const laneLetter = form => String.fromCharCode(65 + PARALLEL_IDS.indexOf(form.add(FORM_ID).readS32()));

// Traktor's stem controls are always hidden, whatever the lane's height:
// the custom stems panel replaces them (as on macOS). They are hidden the
// way Traktor hides them for a track without stems. Traktor's
// StemControls::setShown (no symbol on Windows; found by its code) sets
// STEMS_SHOWN to STEMS_CAPABLE && shown, and shows or hides every stem
// control and the collapse switch with it; Traktor calls it with true when
// a track with stems loads, and with false otherwise. It is hooked so that
// it always gets false. A track loaded before the hook is hidden from the
// tick, followed by Traktor's own waveform relayout (resizeWaveform), which
// gives the waveform the room it has for a track without stems, as when
// Traktor itself loads one.
// While HIDE_STEMS_DRY_RUN is true nothing is changed: the hooked calls,
// each lane's stem state and what would be done are reported
// (dryRunHideStems).
const STOCK_LANE_HEIGHT = 91;
const HIDE_STEMS_DRY_RUN = false;
const STEMS_CAPABLE = 0x18;     // u8
const STEMS_SHOWN = 0x1c;       // u8
const STEMS_SWITCH = 0x1a8;     // the collapse switch (the arrow)
const CONTROL_VISIBLE = 0x95;   // u8, any NGL control
const CONTROL_LEFT = 0x48;
// RVAs on Traktor 4.5.1, checked against their first bytes.
const SET_STEMS_SHOWN = {rva: 0xb6d0f0, bytes: [
  0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48,
  0x83, 0xec, 0x30, 0x0f, 0xb6, 0x41, 0x18, 0x48, 0x8b, 0xd9, 0x22, 0xc2]};
const RESIZE_WAVEFORM = {rva: 0xb6c060, bytes: [
  0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48,
  0x83, 0xec, 0x30, 0x48, 0x8b, 0x91, 0x38, 0x06, 0x00, 0x00, 0x48, 0x8b]};
let setStemsShown = null;
let resizeWaveform = null;
let settingStems = false;
const reportedHide = new Map();  // lane form -> its stem state last reported

const tallLanes = () => laneHeight > STOCK_LANE_HEIGHT;

function traktorFunction(f, name) {
  const p = module.base.add(f.rva);
  const bytes = Array.from(new Uint8Array(p.readByteArray(f.bytes.length)));
  if (bytes.some((b, i) => b !== f.bytes[i])) {
    send({traktorFunction: name + ': unexpected bytes (another Traktor version?), not used'});
    return null;
  }
  return p;
}

function hookStemsShown() {
  const shownAddr = traktorFunction(SET_STEMS_SHOWN, 'setStemsShown');
  const resizeAddr = traktorFunction(RESIZE_WAVEFORM, 'resizeWaveform');
  if (shownAddr === null || resizeAddr === null) return;
  setStemsShown = new NativeFunction(shownAddr, 'void', ['pointer', 'uint8']);
  resizeWaveform = new NativeFunction(resizeAddr, 'void', ['pointer']);
  Interceptor.attach(shownAddr, {onEnter(args) {
    if (settingStems || (args[1].toUInt32() & 0xff) === 0) return;
    if (HIDE_STEMS_DRY_RUN) {
      send({dryRunHideStems: {call: 'setShown(true)', action: 'would pass false'}});
      return;
    }
    args[1] = ptr(0);
  }});
}

function hideStems(form) {
  if (setStemsShown === null) return;
  const stems = form.add(FORM_STEMS).readPointer();
  if (stems.isNull()) return;
  const shown = stems.add(STEMS_SHOWN).readU8();
  if (HIDE_STEMS_DRY_RUN) {
    const arrow = stems.add(STEMS_SWITCH).readPointer();
    const wave = form.add(FORM_CONTROL).readPointer();
    const state = {letter: laneLetter(form), capable: stems.add(STEMS_CAPABLE).readU8(), shown,
                   arrowVisible: arrow.isNull() ? null : arrow.add(CONTROL_VISIBLE).readU8(),
                   waveLeft: wave.isNull() ? null : wave.add(CONTROL_LEFT).readS32()};
    const key = JSON.stringify(state);
    if (reportedHide.get(form.toString()) === key) return;
    reportedHide.set(form.toString(), key);
    send({dryRunHideStems: Object.assign(state, shown ? {action: 'would hide'} : {})});
    return;
  }
  if (shown === 0) return;
  settingStems = true;
  try {
    setStemsShown(stems, 0);
    resizeWaveform(form);
  } finally {
    settingStems = false;
  }
}

// The deck letter and the waveform zoom buttons on the right edge are placed
// by the compiled-in form for Traktor's 91 px lane, so a taller lane leaves
// them at its top. They are moved down, as a block, to the middle of the
// lane (as on macOS), from their top and bottom as first seen, so the move
// is the same however often it is redone; left and right stay Traktor's.
// Traktor's Form::getControl (no symbol on Windows; it walks the form's
// control list for the control with that ID at CONTROL_ID) finds them, and
// each control's own setPosition (vtable slot CONTROL_SET_POSITION) moves
// it, so it is laid out and repainted. A control
// not found is skipped.
// While CENTRE_DRY_RUN is true nothing is moved: each lane's controls and
// where they would go are reported (dryRunCentre).
const CENTRE_DRY_RUN = false;
const DECK_LETTER = 129;
const ZOOM_IDS = [32, 34, 33];   // top (+), middle (=), bottom (-)
const CENTRED_IDS = [DECK_LETTER].concat(ZOOM_IDS);
const FORM_BASE = 0x18;          // NGL::Form subobject
const CONTROL_ID = 0x58;
const CONTROL_SET_POSITION = 0x40;
const GET_CONTROL = {rva: 0x1e0fea0, bytes: [
  0x48, 0x8b, 0x81, 0x88, 0x00, 0x00, 0x00, 0x44, 0x8b, 0xca, 0x48, 0x8b,
  0x08, 0x48, 0x3b, 0xc1, 0x74, 0x24, 0x0f, 0x1f, 0x40, 0x00, 0x66, 0x66]};
let getControl = null;
const centredControls = new Map(); // lane form -> [{id, control}] (control null if not found)
const stockRects = new Map();      // control -> [left, top, right, bottom] as first seen
const reportedCentre = new Map();  // lane form -> report last sent
const moveRect = Memory.alloc(16);

function centreControls(form) {
  if (getControl === null || !tallLanes()) return;
  const key = form.toString();
  if (!centredControls.has(key)) {
    centredControls.set(key, CENTRED_IDS.map(id => {
      const control = getControl(form.add(FORM_BASE), id);
      return {id, control: control.isNull() || control.add(CONTROL_ID).readU32() !== id ? null : control};
    }));
  }
  const height = form.add(FORM_HEIGHT).readS32();
  const offset = Math.max(0, Math.round((height - STOCK_LANE_HEIGHT) / 2));
  const moves = [];
  for (const {id, control} of centredControls.get(key)) {
    if (control === null) {
      moves.push({id, found: false});
      continue;
    }
    const r = [0, 4, 8, 12].map(o => control.add(CONTROL_LEFT + o).readS32());
    const c = control.toString();
    if (!stockRects.has(c)) stockRects.set(c, r);
    const stock = stockRects.get(c);
    const target = [r[0], stock[1] + offset, r[2], stock[3] + offset];
    moves.push({id, control, rect: r, newRect: target, moved: r.some((v, i) => v !== target[i])});
  }
  if (CENTRE_DRY_RUN) {
    const report = JSON.stringify({letter: laneLetter(form), height, offset,
        controls: moves.map(m => m.found === false ? {id: m.id, found: false}
                                                   : {id: m.id, rect: m.rect, newRect: m.newRect})});
    if (reportedCentre.get(key) === report) return;
    reportedCentre.set(key, report);
    send({dryRunCentre: JSON.parse(report)});
    return;
  }
  for (const m of moves) {
    if (!m.moved) continue;
    m.newRect.forEach((v, i) => moveRect.add(4 * i).writeS32(v));
    const setPosition = new NativeFunction(
        m.control.readPointer().add(CONTROL_SET_POSITION).readPointer(), 'void', ['pointer', 'pointer']);
    setPosition(m.control, moveRect);
  }
}

// Lane panels (qml/LanePanel.qml) are Qt windows of this same process, titled
// "TraktorLanePanel X": one over the left end of each lane, "X info" over its
// right end, up to the lane's end (it covers Traktor's zoom buttons), and
// "X stems" right of the left one, against it, or in its place while the
// left one is hidden. The left and stems panels start after Traktor's deck
// letter (LETTER_GAP). The settings
// button and window (qml/ConfigButton.qml, ConfigWindow.qml) are titled
// "WaveLanes button" and "WaveLanes config". They are all placed from
// the UI tick, on the thread that owns them and in step with Traktor's own
// layout, so they follow the lanes without lag; the tick is a generic NGL
// form method, so it also runs outside the Parallel view, for the button.
// They are made owned windows of the main window, so they stay above it only
// and minimise with it. Each is placed with its own width, as QML set it
// (settings window). Geometry is in Traktor pixels at 100 % scaling: per lane
// a 1 px padding slot and the lane, from lane A's host rect.
//
// QML never hides them; it says what it wants in the title, and this script
// shows or hides them:
//  - BROWSER_SUFFIX: the browser is maximised, all panels hidden;
//  - HIDDEN_TAG: that panel is off (MIDI button, settings, no stems...);
//  - OPEN_TAG: the settings window is to be seen.
// Outside the Parallel view lane A's host is hidden (HOST_VISIBLE), and so
// are the panels.
const PANEL_TITLE = 'TraktorLanePanel ';
const EXTRA_TITLE = 'WaveLanes ';
const BROWSER_SUFFIX = ' browser';
const INFO_TAG = ' info';
const STEMS_TAG = ' stems';
const HIDDEN_TAG = ' hidden';
const OPEN_TAG = ' open';
const HEADER_HEIGHT = 33;
const LANE_PADDING = 1;
// Traktor's deck letter, at the lane's start: in Parallel the waveform
// starts this far into the lane.
const LETTER_GAP = 28;
const PANEL_MARGIN = 4;          // keep clear of the lane's bottom border
const BUTTON_LEFT = 224;         // the logo ends about 215 px from the window's left edge
const BUTTON_SIZE = 22;
const SYNC_MS = 50;              // from the ticks of forms other than lane A
const WINDOW_SCAN_MS = 2000;
const RAISE_MS = 500;
const VISIBILITY_POLL_MS = 100;
const GWLP_HWNDPARENT = -8;
const SWP_NOSIZE = 0x1;
const SWP_NOMOVE = 0x2;
const SWP_NOZORDER = 0x4;
const SWP_NOACTIVATE = 0x10;

const user32 = Process.getModuleByName('user32.dll');
// Exclusive: the script engine stays locked during the call. With Frida's
// default it is released, so the visibility poll and the UI tick could run
// at once, and each read the other's titles and rects from the shared
// buffers below (garbled names: hidden panels shown for a moment).
const win32 = (name, ret, args) => new NativeFunction(user32.getExportByName(name), ret, args, {scheduling: 'exclusive'});
const EnumWindows = win32('EnumWindows', 'int', ['pointer', 'pointer']);
const GetWindowThreadProcessId = win32('GetWindowThreadProcessId', 'uint32', ['pointer', 'pointer']);
const IsWindowVisible = win32('IsWindowVisible', 'int', ['pointer']);
const IsWindow = win32('IsWindow', 'int', ['pointer']);
// Unlike GetWindowTextW, reads the stored title without sending WM_GETTEXT,
// which would wait on whichever (possibly busy) thread owns the window.
const InternalGetWindowText = win32('InternalGetWindowText', 'int', ['pointer', 'pointer', 'int']);
const GetClientRect = win32('GetClientRect', 'int', ['pointer', 'pointer']);
const GetWindowRect = win32('GetWindowRect', 'int', ['pointer', 'pointer']);
const ClientToScreen = win32('ClientToScreen', 'int', ['pointer', 'pointer']);
const GetDpiForWindow = win32('GetDpiForWindow', 'uint32', ['pointer']);
const GetForegroundWindow = win32('GetForegroundWindow', 'pointer', []);
const GetWindow = win32('GetWindow', 'pointer', ['pointer', 'uint32']);
const GW_HWNDNEXT = 2;
const GetWindowLongPtrW = win32('GetWindowLongPtrW', 'pointer', ['pointer', 'int']);
const SetWindowLongPtrW = win32('SetWindowLongPtrW', 'pointer', ['pointer', 'int', 'pointer']);
const SetWindowPos = win32('SetWindowPos', 'int', ['pointer', 'pointer', 'int', 'int', 'int', 'int', 'uint32']);
const ShowWindowAsync = win32('ShowWindowAsync', 'int', ['pointer', 'int']);
const SW_HIDE = 0;
const SW_SHOWNOACTIVATE = 4;

const titleBuf = Memory.alloc(512);
const pidBuf = Memory.alloc(4);
const rectBuf = Memory.alloc(16);
const pointBuf = Memory.alloc(8);
let mainWindow = null;
let windows = [];                // [{hwnd, extra, name, placed, shown}]
let lastScan = 0;
let lastRaise = 0;
let lastCheck = 0;
let lastSync = 0;
let panelError = false;
let reportedLane = '';

function windowTitle(hwnd) {
  InternalGetWindowText(hwnd, titleBuf, 256);
  return titleBuf.readUtf16String();
}

function clientArea(hwnd) {
  GetClientRect(hwnd, rectBuf);
  return rectBuf.add(8).readS32() * rectBuf.add(12).readS32();
}

function windowSize(hwnd) {
  GetWindowRect(hwnd, rectBuf);
  return [rectBuf.add(8).readS32() - rectBuf.readS32(), rectBuf.add(12).readS32() - rectBuf.add(4).readS32()];
}

// The main window is this process's largest visible window with a title
// that is none of ours. Ours are taken whether visible or not, since this
// script hides them.
const enumWindow = new NativeCallback((hwnd, _) => {
  GetWindowThreadProcessId(hwnd, pidBuf);
  if (pidBuf.readU32() !== Process.id) return 1;
  const title = windowTitle(hwnd);
  if (title.startsWith(PANEL_TITLE) || title.startsWith(EXTRA_TITLE)) {
    const known = windows.find(w => w.hwnd.equals(hwnd));
    scanned.windows.push(known || {hwnd, extra: title.startsWith(EXTRA_TITLE), name: '', placed: '', shown: null});
  } else if (title !== '' && IsWindowVisible(hwnd)
             && (scanned.main === null || clientArea(hwnd) > clientArea(scanned.main))) {
    scanned.main = hwnd;
  }
  return 1;
}, 'int', ['pointer', 'pointer']);
let scanned = null;

function scanWindows() {
  scanned = {main: null, windows: []};
  EnumWindows(enumWindow, NULL);
  if (scanned.main === null || mainWindow === null || !scanned.main.equals(mainWindow)) {
    for (const w of scanned.windows) w.placed = '';
  }
  mainWindow = scanned.main;
  windows = scanned.windows;
}

const isInfo = w => w.name.includes(INFO_TAG);
const isStems = w => w.name.includes(STEMS_TAG);
const isLeft = w => !w.extra && !isInfo(w) && !isStems(w);
const kind = w => w.name.split(' ')[0];

// Whether a window should be seen, or null to leave it alone.
function wanted(w, lanesShown) {
  if (w.extra) {
    if (kind(w) === 'button') return true;
    if (kind(w) === 'config') return w.name.endsWith(OPEN_TAG);
    return null;
  }
  return lanesShown === null ? null : lanesShown && !w.name.includes(HIDDEN_TAG);
}

// Traktor draws its drop-down and context menus (NI::NGL::PopupMenu) inside
// its main window, so they would open under the panels, which are windows of
// their own above it. While one is open the panels are hidden like for the
// browser. PopupMenu::m_pMasterPopup (a static; no symbol on Windows) points
// to the open menu and is null with none: opening a menu sets it if it is
// null, and closing one (PopupMenu's vtable slot 24) clears it if it is that
// menu, with `cmp rbx, [m_pMasterPopup]; jne; mov qword [m_pMasterPopup], 0`.
// Its address is taken from that instruction, checked against its bytes on
// Traktor 4.5.1. It is only read.
const MASTER_POPUP_CHECK = {rva: 0x1e1249c, bytes: [
  0x48, 0x3b, 0x1d, 0x65, 0x2b, 0xfe, 0x1f, 0x75, 0x0b, 0x48,
  0xc7, 0x05, 0x58, 0x2b, 0xfe, 0x1f, 0x00, 0x00, 0x00, 0x00]};
const masterPopup = (() => {
  const insn = traktorFunction(MASTER_POPUP_CHECK, 'masterPopup');
  return insn === null ? null : insn.add(7).add(insn.add(3).readS32());
})();
let menuWasOpen = false;
function menuOpen() {
  if (masterPopup === null) return false;
  const open = !masterPopup.readPointer().isNull();
  if (open !== menuWasOpen) {
    menuWasOpen = open;
    send({menu: open ? 'open' : 'closed'});
  }
  return open;
}

// Whether lane A's host is visible (the Parallel view), or null if it is
// gone. While Traktor quits it frees the lanes, and the visibility poll,
// which then has the stage to itself, would read freed memory: that is taken
// as no lane (laneHost forgotten; lane A's next tick, if any, sets it again),
// and the windows are left as they are.
function laneVisible() {
  if (laneHost === null) return null;
  try {
    return laneHost.add(HOST_VISIBLE).readU8() !== 0;
  } catch (e) {
    laneHost = null;
    return null;
  }
}

// Shows or hides every window as its title says. ShowWindowAsync, since the
// visibility poll runs on the script's own thread.
function updateVisibility() {
  for (const w of windows) {
    w.name = windowTitle(w.hwnd).slice(w.extra ? EXTRA_TITLE.length : PANEL_TITLE.length);
  }
  const first = windows.find(w => !w.extra);
  const visible = laneVisible();
  const lanesShown = visible === null || first === undefined ? null
      : visible && !first.name.endsWith(BROWSER_SUFFIX) && !menuOpen();
  for (const w of windows) {
    const want = dragging ? false : wanted(w, lanesShown);
    if (want === null || want === w.shown) continue;
    ShowWindowAsync(w.hwnd, want ? SW_SHOWNOACTIVATE : SW_HIDE);
    w.shown = want;
    if (want) {
      w.placed = '';
      recheckUntil = Date.now() + RECHECK_MS;
    }
  }
}

// Outside the Parallel view Traktor stops ticking the lanes; the generic
// tick still runs for its other forms, but this keeps the panels hidden
// and shown even if it did not. Only then: while the tick syncs, it is the
// only one at work.
const POLL_IDLE_MS = 300;
setInterval(() => {
  const t0 = Date.now();
  if (t0 - lastSync < POLL_IDLE_MS) return;
  try {
    if (mainWindow !== null) updateVisibility();
  } catch (e) {
    reportPanelError(e);
  }
  stat('pollMs', Date.now() - t0);
}, VISIBILITY_POLL_MS);

// Freeze diagnostics: every STATS_MS, if anything took longer than
// SLOW_MS, the worst times seen: work done in the tick (laneMs for the lane
// forms, syncMs for window placement), in the visibility poll (pollMs), and
// the longest gap between two ticks of lane A while it is shown (gapMs, a
// stall of Traktor's UI thread whoever caused it); the tick calls per
// second; and worst, the single slowest Win32 call made from syncWindows,
// and on which window.
const STATS_MS = 5000;
const SLOW_MS = 150;
const newStats = () => ({laneMs: 0, syncMs: 0, pollMs: 0, gapMs: 0, worst: {ms: 0}});
let stats = newStats();
let tickCalls = 0;
let lastLaneTick = 0;

function stat(name, ms) {
  if (ms > stats[name]) stats[name] = ms;
}

// Runs a Win32 call and keeps it as the worst if it is the slowest yet.
function timed(op, w, call) {
  const t0 = Date.now();
  const result = call();
  const ms = Date.now() - t0;
  if (ms > stats.worst.ms) {
    stats.worst = {ms, op, window: w === null ? 'main' : (w.extra ? EXTRA_TITLE : PANEL_TITLE) + w.name};
  }
  return result;
}

setInterval(() => {
  const s = stats;
  const calls = tickCalls;
  stats = newStats();
  tickCalls = 0;
  const {worst, ...times} = s;
  if (Object.values(times).some(ms => ms > SLOW_MS)) {
    send({slow: Object.assign(times, {ticksPerSec: Math.round(calls * 1000 / STATS_MS)},
                              worst.ms > 0 ? {worst} : {})});
  }
}, STATS_MS);

function reportPanelError(e) {
  if (!panelError) send({panelError: String(e), where: e && e.stack ? String(e.stack) : null});
  panelError = true;
}

// The panels and the settings button are made by the controller mapping
// that carries them (Controller Manager > Kontrol Z1 MK2). With none of them
// MAPPING_WAIT_MS after Traktor's main window is found, the mapping is
// missing, and wave_height.py says how to add it (as on macOS).
const MAPPING_WAIT_MS = 10000;
let mainFoundAt = 0;
let mappingChecked = false;
function checkMapping() {
  if (mappingChecked || mainWindow === null) return;
  if (windows.length > 0) {
    mappingChecked = true;
    send({mappingFound: mainFoundAt === 0 ? 0 : Date.now() - mainFoundAt});
  } else if (mainFoundAt === 0) {
    mainFoundAt = Date.now();
  } else if (Date.now() - mainFoundAt >= MAPPING_WAIT_MS) {
    mappingChecked = true;
    send({noMapping: true});
  }
}

// From the UI tick: find the windows, show or hide them, and place them.
function syncWindows() {
  const now = Date.now();
  lastSync = now;
  if (now - lastScan > WINDOW_SCAN_MS || (mainWindow !== null && !IsWindow(mainWindow))) {
    lastScan = now;
    timed('scan', null, scanWindows);
  }
  checkMapping();
  if (mainWindow === null || windows.length === 0) return;
  hookDrag();
  updateVisibility();
  if (now - lastCheck > RAISE_MS || now < recheckUntil) {
    lastCheck = now;
    checkPlaced();
  }
  placeWindows();
  // Traktor sometimes drops our windows below its main window, e.g. when a
  // modal dialog closes. Raise them again, but only while Traktor's main
  // window is in front, so they never cover other applications, and only
  // those that are below it: SetWindowPos runs Qt's handling of the window
  // on this thread.
  if (now - lastRaise > RAISE_MS && GetForegroundWindow().equals(mainWindow)) {
    lastRaise = now;
    for (const w of windows) {
      if (w.shown && !aboveMain(w.hwnd)) {
        timed('raise', w, () => SetWindowPos(w.hwnd, NULL, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE));
      }
    }
  }
}

// A window is only moved when where it should go changes, but something else
// can move it: Qt sometimes applies its own geometry to a window just shown,
// after this script placed it (seen at startup and after dragging the main
// window). Where each window really is is checked, without sending it
// anything; one out of place is placed again. Every RAISE_MS, and on every
// tick for RECHECK_MS after a window is shown, when it happens.
const RECHECK_MS = 1500;
let recheckUntil = 0;
function checkPlaced() {
  for (const w of windows) {
    if (!w.shown || w.placed === '') continue;
    GetWindowRect(w.hwnd, rectBuf);
    const l = rectBuf.readS32(), t = rectBuf.add(4).readS32();
    const actual = [l, t, rectBuf.add(8).readS32() - l, rectBuf.add(12).readS32() - t].join(',');
    if (actual === w.placed) continue;
    const name = (w.extra ? EXTRA_TITLE : PANEL_TITLE) + w.name;
    const report = name + ' ' + actual + ' ' + w.placed;
    if (!reportedMisplaced.has(report)) {
      reportedMisplaced.add(report);
      send({misplaced: {window: name, was: actual, expected: w.placed,
                        msAfterShown: Date.now() - (recheckUntil - RECHECK_MS)}});
    }
    w.placed = '';
  }
}
const reportedMisplaced = new Set();

// Whether hwnd is above the main window in the z-order: the main window is
// found walking down from it. Reads the window list without sending anything.
function aboveMain(hwnd) {
  for (let next = GetWindow(hwnd, GW_HWNDNEXT); !next.isNull(); next = GetWindow(next, GW_HWNDNEXT)) {
    if (next.equals(mainWindow)) return true;
  }
  return false;
}

// Lane A's rect in the main window's client area (Traktor pixels), or null.
// It already leaves out the 3 px separators on the window's left and right.
function laneRect() {
  if (laneHost === null || laneHeight <= 0) return null;
  const r = [0, 4, 8, 12].map(o => laneHost.add(HOST_RECT + o).readS32());
  const key = r.join(',');
  if (key !== reportedLane) {
    reportedLane = key;
    send({laneRect: r});
  }
  return {left: r[0], top: r[1], right: r[2]};
}

// The width of lane <letter>'s left panel, or 0 while it is hidden.
function leftPanelWidth(letter) {
  const left = windows.find(w => isLeft(w) && w.name[0] === letter);
  return left === undefined || !left.shown ? 0 : windowSize(left.hwnd)[0];
}

function placeWindows() {
  pointBuf.writeS32(0);
  pointBuf.add(4).writeS32(0);
  ClientToScreen(mainWindow, pointBuf);
  const x = pointBuf.readS32(), y = pointBuf.add(4).readS32();
  GetClientRect(mainWindow, rectBuf);
  const clientWidth = rectBuf.add(8).readS32(), clientHeight = rectBuf.add(12).readS32();
  const scale = GetDpiForWindow(mainWindow) / 96;
  const px = v => Math.round(v * scale);
  const lane = laneRect();
  const moves = [];
  for (const w of windows) {
    if (!w.shown) continue;
    const [width, height] = windowSize(w.hwnd);
    let rect = null;
    let flags = SWP_NOZORDER | SWP_NOACTIVATE;
    if (w.extra && kind(w) === 'button') {
      rect = [x + px(BUTTON_LEFT), y + px((HEADER_HEIGHT - BUTTON_SIZE) / 2), width, height];
      flags |= SWP_NOSIZE;
    } else if (w.extra) {
      rect = [x + Math.round((clientWidth - width) / 2), y + Math.round((clientHeight - height) / 2), width, height];
      flags |= SWP_NOSIZE;
    } else if (lane !== null) {
      const index = w.name.charCodeAt(0) - 65;
      const top = y + px(lane.top + index * (laneHeight + LANE_PADDING));
      let left = x + px(lane.left + LETTER_GAP);
      if (isInfo(w)) {
        left = x + px(lane.right) - width;
      } else if (isStems(w)) {
        left += leftPanelWidth(w.name[0]);
      }
      rect = [left, top, width, px(laneHeight - PANEL_MARGIN)];
    }
    if (rect === null) continue;
    if (!GetWindowLongPtrW(w.hwnd, GWLP_HWNDPARENT).equals(mainWindow)) {
      timed('owner', w, () => SetWindowLongPtrW(w.hwnd, GWLP_HWNDPARENT, mainWindow));
    }
    const key = rect.join(',');
    if (key !== w.placed) {
      moves.push({w, rect, flags});
      w.placed = key;
    }
  }
  for (const {w, rect, flags} of moves) {
    timed('place', w, () => SetWindowPos(w.hwnd, NULL, rect[0], rect[1], rect[2], rect[3], flags));
  }
}

// While Traktor's main window is being dragged (or resized by its frame), all
// our windows are hidden: placed from the UI tick they trail it, and placing
// them costs too much to do on every step of the drag (following
// EVENT_OBJECT_LOCATIONCHANGE slowed down the whole drag). Windows reports
// only the start and the end of the drag (EVENT_SYSTEM_MOVESIZESTART/END,
// the only events asked for, so nothing else reaches the script). Registered
// out of context from the UI tick, the reports arrive on Traktor's UI
// thread, as messages. At the end the windows are placed, then shown: the
// show is asynchronous, and goes through after the placing.
const EVENT_SYSTEM_MOVESIZESTART = 0x000a;
const EVENT_SYSTEM_MOVESIZEEND = 0x000b;
const OBJID_WINDOW = 0;
const WINEVENT_OUTOFCONTEXT = 0;
const SetWinEventHook = win32('SetWinEventHook', 'pointer',
                              ['uint32', 'uint32', 'pointer', 'pointer', 'uint32', 'uint32', 'uint32']);
let dragging = false;
let dragHook = null;
const onMoveSize = new NativeCallback((hook, event, hwnd, idObject, idChild, thread, time) => {
  if (idObject !== OBJID_WINDOW || mainWindow === null || !hwnd.equals(mainWindow)) return;
  try {
    dragging = event === EVENT_SYSTEM_MOVESIZESTART;
    updateVisibility();
    if (!dragging) placeWindows();
    lastSync = Date.now();
  } catch (e) {
    reportPanelError(e);
  }
}, 'void', ['pointer', 'uint32', 'pointer', 'int32', 'int32', 'uint32', 'uint32']);

function hookDrag() {
  if (dragHook !== null) return;
  dragHook = SetWinEventHook(EVENT_SYSTEM_MOVESIZESTART, EVENT_SYSTEM_MOVESIZEEND, NULL,
                             onMoveSize, Process.id, 0, WINEVENT_OUTOFCONTEXT);
  send({dragHook: dragHook.isNull() ? 'failed' : 'on'});
}

// One scan at startup, only to find a lane form and through it the methods
// to hook; afterwards lane forms are recognised as they pass through the tick.
function findLaneForm() {
  for (const r of Process.enumerateRanges({protection: 'rw-', coalesce: true})) {
    try {
      for (const h of Memory.scanSync(r.base, r.size, pattern(formVtable))) {
        if (isLaneForm(h.address)) return h.address;
      }
    } catch (e) {
      // Ranges can be freed or re-protected while scanning.
    }
  }
  return null;
}

// Patch first: when wave_height.py launches Traktor this runs before any
// buffer exists. The lane forms only appear once the main window is built.
send({waveBuffer: patchWaveBuffer()});

function hookLanes(first) {
  // Every lane has the layout's height; lane A's tick keeps it up to date.
  laneHeight = first.add(FORM_HEIGHT).readS32();
  hookStemsShown();
  const getControlAddr = traktorFunction(GET_CONTROL, 'getControl');
  if (getControlAddr !== null) getControl = new NativeFunction(getControlAddr, 'pointer', ['pointer', 'uint32']);

  const tick = first.add(UI_TICK_SUBOBJECT).readPointer().add(UI_TICK_SLOT * 8).readPointer();
  Interceptor.attach(tick, {
    onEnter(args) {
      tickCalls++;
      const form = args[0].sub(UI_TICK_SUBOBJECT);
      this.form = isLaneForm(form) ? form : null;
    },
    onLeave() {
      const t0 = Date.now();
      if (this.form === null) {
        // Any other form: keeps the button and panels in step outside the
        // Parallel view, where the lanes stop ticking.
        if (t0 - lastSync < SYNC_MS) return;
      } else {
        try {
          stretchWave(this.form);
          hideStems(this.form);
          centreControls(this.form);
        } catch (e) {
          // Form torn down during the call.
          return;
        }
        stat('laneMs', Date.now() - t0);
        if (this.form.add(FORM_ID).readS32() !== PARALLEL_IDS[0]) return;
        if (laneHost !== null && laneHost.add(HOST_VISIBLE).readU8() !== 0) {
          if (lastLaneTick !== 0) stat('gapMs', t0 - lastLaneTick);
          lastLaneTick = t0;
        } else {
          lastLaneTick = 0;
        }
      }
      const t1 = Date.now();
      try {
        syncWindows();
      } catch (e) {
        reportPanelError(e);
      }
      stat('syncMs', Date.now() - t1);
    },
  });
  send({ready: true});
}

// Off the load path, so a launched Traktor can be resumed right away; retried
// until the main window (and its lanes) exist. Nothing is hooked yet, so the
// scans cannot stall the UI thread.
function waitForLanes() {
  const first = findLaneForm();
  if (first === null) setTimeout(waitForLanes, 3000);
  else hookLanes(first);
}
setTimeout(waitForLanes, 0);
