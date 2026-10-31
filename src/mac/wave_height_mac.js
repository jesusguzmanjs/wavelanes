// Stretch Traktor's parallel waveforms to the height of their layout slot
// (macOS / arm64 port of wave_height.js).
//
// The parallel lane forms (DeckWaveDisplayForm, form IDs 885-888) take their
// height from the layout XML, but the WaveformControl inside them keeps the
// geometry of the compiled-in form definition, 87 px tall. Traktor's own
// DeckWaveDisplayForm::resizeWaveform() only fits the control horizontally,
// keeping its top and bottom; after it returns, this script moves the bottom
// to the form's height minus Traktor's 4 px margin, through the same virtual
// setPosition() Traktor calls, so the control is laid out and repainted as
// usual. resizeWaveform runs on the UI thread on every lane layout, so no
// memory scan and no per-frame hook are needed.
//
// The Mac binary keeps its C++ symbols, so functions are looked up by name.
// Field offsets were read on Traktor Pro 4.5.0 (arm64) and may change.

const FORM_ID = 0x24;            // u32: NGL::Form subobject (+0x18) + 0xc, see Form::setID
const FORM_HEIGHT = 0x44;        // s32: Form visible size (+0x18 + 0x28) height
const FORM_CONTROL = 0x338;      // WaveformControl*
const CONTROL_RECT = 0x38;       // s32 left, top, right, bottom
const SET_POSITION_SLOT = 0x48;  // NGL::Control::setPosition(Rect const&)
const MARGIN = 4;
const PARALLEL_IDS = [885, 886, 887, 888];

// Set by wave_height_mac.py. While true nothing is changed: every write the
// script would make is reported instead.
const DRY_RUN = true;

const main = Process.mainModule;

function symbol(name) {
  const a = main.findSymbolByName(name);
  if (a === null) throw new Error('symbol not found: ' + name);
  return a;
}

const resizeWaveformAddr = symbol('_ZN19DeckWaveDisplayForm14resizeWaveformEv');
const resizeWaveform = new NativeFunction(resizeWaveformAddr, 'void', ['pointer']);
const updateControlsAddr = symbol('_ZN19DeckWaveDisplayForm12StemControls14updateControlsEv');
const updateControls = new NativeFunction(updateControlsAddr, 'void', ['pointer']);
const rect = Memory.alloc(16);
const reported = new Map();
let laneHeight = 0;
let busy = false;

function isLane(form) {
  return PARALLEL_IDS.includes(form.add(FORM_ID).readU32());
}

const FORM_STEMS = 0x618;        // DeckWaveDisplayForm::StemControls*
const seenLanes = new Set();

// Traktor's stem controls are always hidden: the stems panel (QML) takes
// their place, and the copy is not the place for Traktor's own view.
// StemControls::updateControls() shows or hides them all (rows, icons,
// dividers, the collapse arrow, the colour bars on the right) from one byte,
// STEMS_SHOWN, which Traktor sets to capable && shown just before calling it
// (setDAWView() sets it on a stem track, a track unload clears it; the
// function setShown() of the Windows build is inlined into those on Mac).
// Clearing it on entry leaves the lane as Traktor leaves it for a track
// without stems. A lane already showing them when the script attaches is
// hidden once, when first seen (hideStemControls). The deck letter and the
// zoom buttons are not stem controls, and stay.
// While HIDE_DRY_RUN is true nothing is written: it is reported instead.
const HIDE_DRY_RUN = false;
const STEMS_SHOWN = 0x1c;        // u8 in StemControls, read by updateControls()
const reportedHide = new Set();

function reportHide(stems, where) {
  const key = stems.toString();
  if (reportedHide.has(key)) return;
  reportedHide.add(key);
  send({dryRunHide: {stems: key, where, shown: stems.add(STEMS_SHOWN).readU8()}});
}

Interceptor.attach(updateControlsAddr, {
  onEnter(args) {
    const stems = args[0];
    if (stems.add(STEMS_SHOWN).readU8() === 0) return;
    if (HIDE_DRY_RUN) {
      reportHide(stems, 'updateControls');
      return;
    }
    stems.add(STEMS_SHOWN).writeU8(0);
  },
});

// A lane whose stem controls are shown when first seen: hide them as Traktor
// would (updateControls), then lay the lane out again.
function hideStemControls(form) {
  const stems = form.add(FORM_STEMS).readPointer();
  if (stems.isNull() || stems.add(STEMS_SHOWN).readU8() === 0) return;
  if (HIDE_DRY_RUN) {
    reportHide(stems, 'lane ' + form.add(FORM_ID).readU32());
    return;
  }
  const wasBusy = busy;
  busy = true;
  try {
    updateControls(stems);       // the hook above clears STEMS_SHOWN first
    resizeWaveform(form);
  } finally {
    busy = wasBusy;
  }
}

function stretchWave(form) {
  if (!isLane(form)) return;
  const wave = form.add(FORM_CONTROL).readPointer();
  if (wave.isNull()) return;
  const height = form.add(FORM_HEIGHT).readS32();
  if (height !== laneHeight) {
    // Lanes stretch with the window; wave_height_mac.py places the panels with it.
    laneHeight = height;
    send({laneHeight: height});
  }
  const r = [0, 4, 8, 12].map(o => wave.add(CONTROL_RECT + o).readS32());
  const bottom = height - MARGIN;
  if (bottom <= r[1] || r[3] === bottom) return;

  if (DRY_RUN) {
    const key = form.toString();
    const plan = r.slice(0, 3).concat(bottom).join(',');
    if (reported.get(key) !== plan) {
      reported.set(key, plan);
      send({dryRun: {id: form.add(FORM_ID).readU32(), rect: r, newRect: plan.split(',').map(Number)}});
    }
    return;
  }
  rect.writeS32(r[0]);
  rect.add(4).writeS32(r[1]);
  rect.add(8).writeS32(r[2]);
  rect.add(12).writeS32(bottom);
  const setPosition = new NativeFunction(
      wave.readPointer().add(SET_POSITION_SLOT).readPointer(), 'void', ['pointer', 'pointer']);
  setPosition(wave, rect);
}

// The deck letter and Traktor's waveform zoom buttons are controls of the
// lane form, placed by the compiled-in form definition for Traktor's 91 px
// lane, so a taller lane leaves them at its top. They are moved down by half
// the extra height, as a block, through the same setPosition() as the
// waveform, from their own top and bottom as first seen, so a layout that
// resets them or not ends the same; the left and right stay Traktor's. The
// controls are found with Traktor's own Form::getControl (IDs read on Traktor
// Pro 4.5.0), and a missing one is skipped. While CENTRE_DRY_RUN is true
// nothing is moved: the moves are reported.
const CENTRE_DRY_RUN = false;
const DECK_LETTER = 129;
const ZOOM_IDS = [32, 33, 34];   // waveform zoom buttons on the right edge: +, −, =
const CENTRED_IDS = [DECK_LETTER].concat(ZOOM_IDS);
const STOCK_HEIGHT = 91;
const FORM_BASE = 0x18;          // NGL::Form subobject
const getControl = new NativeFunction(
    symbol('_ZNK2NI3NGL4Form10getControlEj'), 'pointer', ['pointer', 'uint']);
const stockRects = new Map();    // control -> its rect as first seen
const reportedCentre = new Map(); // form -> height last reported

function centreControls(form) {
  if (!isLane(form)) return;
  const height = form.add(FORM_HEIGHT).readS32();
  const offset = Math.max(0, Math.round((height - STOCK_HEIGHT) / 2));
  const moves = [];
  for (const id of CENTRED_IDS) {
    const control = getControl(form.add(FORM_BASE), id);
    if (control.isNull()) continue;
    const r = [0, 4, 8, 12].map(o => control.add(CONTROL_RECT + o).readS32());
    const key = control.toString();
    if (!stockRects.has(key)) stockRects.set(key, r);
    const stock = stockRects.get(key);
    const target = [r[0], stock[1] + offset, r[2], stock[3] + offset];
    if (r.every((v, i) => v === target[i])) continue;
    moves.push({id, control, rect: r, newRect: target});
  }
  if (CENTRE_DRY_RUN) {
    const key = form.toString();
    if (moves.length === 0 || reportedCentre.get(key) === height) return;
    reportedCentre.set(key, height);
    send({dryRunStemMoves: {id: form.add(FORM_ID).readU32(), height, offset, layout: 'centre',
                            moves: moves.map(m => ({id: m.id, rect: m.rect, newRect: m.newRect}))}});
    return;
  }
  for (const m of moves) {
    m.newRect.forEach((v, i) => rect.add(4 * i).writeS32(v));
    const setPosition = new NativeFunction(
        m.control.readPointer().add(SET_POSITION_SLOT).readPointer(), 'void', ['pointer', 'pointer']);
    setPosition(m.control, rect);
  }
}

// Lane panels (qml/LanePanel.qml) are Qt windows of this same process, titled
// "TraktorLanePanel X". They are made AppKit child windows of Traktor's main
// window, so they move, hide and minimise with it and stay above it only, and
// are placed over the left end of each lane on every lane layout. The panels
// take lane A's position in the window, from Traktor's own
// Form::translateRectToWindow, since the lanes move down when Traktor shows
// the global section above them on a tall enough window. The layout XML's
// geometry (a header row, then per lane a 1 pt padding slot and the lane) is
// the fallback while lane A is not laid out yet.
//
// The lanes can also move, or be hidden, with no lane layout at all: turning
// the global section off in the preferences, switching to a view other than
// Parallel, or maximising the browser. So syncPanels() also runs every
// POLL_MS on the main thread: it hides the panels while lane A's host
// control is hidden (any view but Parallel) or the browser is maximised
// (the panels add BROWSER_SUFFIX to their title, from QML), and places them
// again when lane A has moved.
//
// Each lane has a second panel, "TraktorLanePanel X info", over its right
// end. A MIDI button hides those (QML adds HIDDEN_TAG to their title); they
// are hidden here like all of them for the browser, and shown again. A third,
// "TraktorLanePanel X stems", goes right of the left one, against it, or in
// its place while the left one is hidden. Both start after Traktor's deck
// letter (LETTER_GAP).
const PANEL_TITLE = 'TraktorLanePanel ';
const BROWSER_SUFFIX = ' browser';
const INFO_TAG = ' info';
const STEMS_TAG = ' stems';
const HIDDEN_TAG = ' hidden';

// The settings button (qml/ConfigButton.qml) sits over Traktor's header just
// after its logo, in every view; the settings window (qml/ConfigWindow.qml)
// adds OPEN_TAG to its title while it should be seen, and is then shown over
// the middle of the main window. Both are child windows of it, like the panels.
const EXTRA_TITLE = 'WaveLanes ';
const OPEN_TAG = ' open';
const BUTTON_LEFT = 224;         // the logo ends about 214 pt from the window's left edge
const BUTTON_SIZE = 22;
const POLL_MS = 100;
const RESTORE_MS = 1000;         // at most one restore a second, e.g. during the full screen animation
const FORM_CONTAINER = 0x78;     // NGL::Form: its container interface, see Form::translateRectToWindow
const CONTAINER_SUBOBJECT = 0xb0;  // that interface in the hosting SubFormControl, see its thunks
const CONTROL_VISIBLE = 0x7d;    // u8: NGL::Control visible flag, see Control::setVisible
const HEADER_HEIGHT = 33;
const LANE_PADDING = 1;
const LEFT_SEPARATOR = 3;
// The panels' widths are set in QML (settings window); each is placed with
// its window's own width. These are the defaults, for a window without one.
const PANEL_WIDTH = 150;
const INFO_WIDTH = 100;          // the info panels, at the lane's right end
// Traktor's deck letter, at the lane's left end where the waveform has not
// started yet (it starts 28 px in), stays in sight: the left panel, or the
// stems panel without it, starts after it.
const LETTER_GAP = 28;
const PANEL_MARGIN = 4;          // keep clear of the lane's bottom border
const FORM_WIDTH = 0x40;         // s32: Form visible size width, next to FORM_HEIGHT
const NS_WINDOW_ABOVE = 1;
const NGL_FORM = 0x18;           // NGL::Form subobject of the lane form

const translateRectToWindow = new NativeFunction(
    symbol('_ZNK2NI3NGL4Form21translateRectToWindowERNS_2GP4RectE'), 'void', ['pointer', 'pointer']);
const laneRect = Memory.alloc(16);
const laneForms = new Map();     // lane form ID -> form, from resizeWaveform

const RECT = ['double', 'double', 'double', 'double'];
const msgSend = Module.getGlobalExportByName('objc_msgSend');
const msg = (ret, args) => new NativeFunction(msgSend, ret, ['pointer', 'pointer'].concat(args));
const msgId = msg('pointer', []);
const msgIdAt = msg('pointer', ['ulong']);
const msgCount = msg('ulong', []);
const msgBool = msg('uint8', []);
const msgRect = msg(RECT, []);
const msgRectRect = msg(RECT, [RECT]);
const msgSetFrame = msg('void', [RECT, 'uint8']);
const msgAddChild = msg('void', ['pointer', 'long']);
const msgVoidId = msg('void', ['pointer']);
const APPKIT_WINDOW_CLASSES = ['_NS', 'NSToolbarFullScreen'];  // full screen helpers
const getClassName = new NativeFunction(Module.getGlobalExportByName('object_getClassName'), 'pointer', ['pointer']);
const isAppKitWindow = w => {
  const name = getClassName(w).readUtf8String();
  return APPKIT_WINDOW_CLASSES.some(prefix => name.startsWith(prefix));
};
const selCache = new Map();
const selRegister = new NativeFunction(Module.getGlobalExportByName('sel_registerName'), 'pointer', ['pointer']);
const objcClass = new NativeFunction(Module.getGlobalExportByName('objc_getClass'), 'pointer', ['pointer']);
const isMainThread = new NativeFunction(Module.getGlobalExportByName('pthread_main_np'), 'int', []);
const NSApplication = objcClass(Memory.allocUtf8String('NSApplication'));
const reportedPanels = new Map();
let warnedThread = false;
let warnedMain = false;
let panelWindows = null;         // {main, panels: [[letter, NSWindow]]}, from findWindows
let panelsShown = true;          // Qt shows them when they are created
let placedAt = null;             // lane A position and height the panels were last placed for
let panelsOff = '';              // the panels hidden by their own title, when last shown
let reportedWidth = null;
const extrasPlaced = new Map();  // 'button' or 'config' -> what it was last shown or hidden for
let lastRestore = 0;

function sel(name) {
  if (!selCache.has(name)) selCache.set(name, selRegister(Memory.allocUtf8String(name)));
  return selCache.get(name);
}

function windowTitle(w) {
  const s = msgId(w, sel('title'));
  return s.isNull() ? '' : msgId(s, sel('UTF8String')).readUtf8String();
}

// [left, top] and right of a lane in window points, or null if it has not
// been laid out. The window may count in pixels on a Retina screen; the scale
// comes from the translated height against the lane's own. right is null if
// the form's width does not look right.
function lanePosition(index, lane) {
  const form = laneForms.get(PARALLEL_IDS[index]);
  if (form === undefined) return null;
  const width = form.add(FORM_WIDTH).readS32();
  if (width !== reportedWidth) {
    reportedWidth = width;
    send({laneWidth: width});
  }
  laneRect.writeS32(0);
  laneRect.add(4).writeS32(0);
  laneRect.add(8).writeS32(width > 2 * PANEL_WIDTH ? width : PANEL_WIDTH);
  laneRect.add(12).writeS32(lane);
  translateRectToWindow(form.add(NGL_FORM), laneRect);
  const r = [0, 4, 8, 12].map(o => laneRect.add(o).readS32());
  const scale = (r[3] - r[1]) / lane;
  // A lane is never at the window's origin; there it is not placed in the
  // window yet (first layout), and the rect comes back untranslated.
  if (!(scale > 0) || (r[0] === 0 && r[1] === 0)) return null;
  return {left: r[0] / scale, top: r[1] / scale, right: width > 2 * PANEL_WIDTH ? r[2] / scale : null, rect: r};
}

const isInfo = name => name.includes(INFO_TAG);
const isStems = name => name.includes(STEMS_TAG);
const isOff = name => name.includes(HIDDEN_TAG);
const offNames = panels => panels.filter(([name]) => isOff(name)).map(([name]) => name).join('|');

// The lane panels and Traktor's main window: the largest other visible window
// with a title. AppKit's own windows are left out: entering or leaving full
// screen shows an untitled transition window as large as the main one, which
// goes away with any child window attached to it.
function findWindows() {
  const windows = msgId(msgId(NSApplication, sel('sharedApplication')), sel('windows'));
  const panels = [];
  const extras = [];
  let main = null;
  let mainArea = 0;
  for (let i = 0, n = msgCount(windows, sel('count')); i < n; i++) {
    const w = msgIdAt(windows, sel('objectAtIndex:'), i);
    const title = windowTitle(w);
    if (title.startsWith(PANEL_TITLE)) {
      panels.push([title.slice(PANEL_TITLE.length), w]);
    } else if (title.startsWith(EXTRA_TITLE)) {
      extras.push([title.slice(EXTRA_TITLE.length), w]);
    } else if (title !== '' && !isAppKitWindow(w) && msgBool(w, sel('isVisible'))) {
      const f = msgRect(w, sel('frame'));
      if (f[2] * f[3] > mainArea) {
        main = w;
        mainArea = f[2] * f[3];
      }
    }
  }
  if (main === null && panels.length + extras.length > 0 && !warnedMain) {
    warnedMain = true;
    const seen = [];
    for (let i = 0, n = msgCount(windows, sel('count')); i < n; i++) {
      const w = msgIdAt(windows, sel('objectAtIndex:'), i);
      seen.push(`${getClassName(w).readUtf8String()} '${windowTitle(w)}' visible=${msgBool(w, sel('isVisible'))}`);
    }
    send({error: 'no main window for the panels; windows: ' + seen.join('; ')});
  }
  return main === null ? null : {main, panels, extras};
}

function placePanels(lane) {
  if (!isMainThread()) {
    // AppKit is main-thread only.
    if (!warnedThread) send({error: 'lane layout is not on the main thread; panels not placed'});
    warnedThread = true;
    return;
  }
  panelWindows = findWindows();
  if (panelWindows === null || panelWindows.panels.length === 0 || !panelsShown) return;
  const {main, panels} = panelWindows;
  const c = contentRect(main);
  const contentTop = c[1] + c[3];  // screen coordinates grow upwards
  const height = lane - PANEL_MARGIN;
  // Lanes are stacked with a 1 pt padding slot between them, so every panel
  // follows lane A's position. Each lane's own position is not used: right
  // after a start that rebuilt the layout, lane C's could still be the one
  // from before the global section appeared (seen once, 83 pt too high).
  const pos = lanePosition(0, lane);
  placedAt = placement(pos, lane, c, panels);
  // The lanes reach the window's right edge, less the same separator as on the left.
  const right = pos === null || pos.right === null ? c[2] - LEFT_SEPARATOR : pos.right;
  for (const [name, w] of panels) {
    const index = name.charCodeAt(0) - 65;
    const step = index * (lane + LANE_PADDING);
    const fallback = HEADER_HEIGHT + LANE_PADDING + step;
    const width = panelWidth(name, w);
    const laneLeft = (pos === null ? LEFT_SEPARATOR : pos.left) + LETTER_GAP;
    const left = isInfo(name) ? right - width
        : isStems(name) ? laneLeft + leftPanelWidth(name, panels) : laneLeft;
    const top = pos === null ? fallback : pos.top + step;
    const frame = [c[0] + left, contentTop - top - height, width, height];
    const off = isOff(name);
    const attach = !off && !msgId(w, sel('parentWindow')).equals(main);
    if (DRY_RUN) {
      const plan = frame.join(',') + attach + off;
      if (reportedPanels.get(name) !== plan) {
        reportedPanels.set(name, plan);
        send({dryRunPanel: {letter: name, main: windowTitle(main), frame, attach, off,
                            laneRect: pos === null ? null : pos.rect, fallbackTop: fallback}});
      }
      continue;
    }
    if (off) {
      hidePanel(main, w);
      continue;
    }
    if (attach) msgAddChild(main, sel('addChildWindow:ordered:'), w, NS_WINDOW_ABOVE);
    msgSetFrame(w, sel('setFrame:display:'), frame, 1);
  }
}

// A hidden child window would be ordered in again with its parent, so it is
// detached first; placePanels attaches it again when shown.
function hidePanel(main, w) {
  msgVoidId(main, sel('removeChildWindow:'), w);
  msgVoidId(w, sel('orderOut:'), NULL);
}

// The main window's content in screen coordinates: the content view's own rect, not
// contentRectForFrameRect:, since in full screen the title bar is gone and the content fills the
// window, which that would still count 28 pt short.
function contentRect(main) {
  return msgRectRect(main, sel('convertRectToScreen:'), msgRect(msgId(main, sel('contentView')), sel('frame')));
}

// What the panels were placed for. The window's content rect is part of it: leaving full screen,
// AppKit moves child windows with the bottom of the main window, not its top, so they end up as
// far off as the window's height changed. So are the panels' widths: a right panel made wider
// in the settings window grows from its left edge, and is moved back to the lane's end.
function placement(pos, lane, c, panels) {
  return (pos === null ? `fallback ${lane}` : `${pos.left},${pos.top} ${lane}`) + ` in ${c.join(',')}`
      + ' widths ' + panels.map(([name, w]) => panelWidth(name, w)).join(',');
}

// The room the left panel of a panel's lane takes: its width, or none while
// it is hidden (the stems panel then takes its place).
function leftPanelWidth(name, panels) {
  const left = panels.find(([n]) => n[0] === name[0] && !isInfo(n) && !isStems(n));
  if (left === undefined || isOff(left[0])) return 0;
  return panelWidth(left[0], left[1]);
}

// A panel's width as QML set it.
function panelWidth(name, w) {
  return Math.round(msgRect(w, sel('frame'))[2]) || (isInfo(name) ? INFO_WIDTH : PANEL_WIDTH);
}

// The control hosting lane A's form in the main form, or null. While Traktor
// quits it frees the lanes, and a read that fails then is taken as no lane:
// the forms are forgotten (the next lane layout, if any, records them again)
// and the windows are left as they are.
function laneHost() {
  const form = laneForms.get(PARALLEL_IDS[0]);
  if (form === undefined) return null;
  try {
    const container = form.add(NGL_FORM + FORM_CONTAINER).readPointer();
    return container.isNull() ? null : container.sub(CONTAINER_SUBOBJECT);
  } catch (e) {
    laneForms.clear();
    return null;
  }
}

// Whether the control is visible, or null if it can no longer be read.
function hostVisible(host) {
  try {
    return host.add(CONTROL_VISIBLE).readU8() !== 0;
  } catch (e) {
    laneForms.clear();
    return null;
  }
}

function showPanels(shown, why) {
  panelsShown = shown;
  const {main, panels} = panelWindows;
  panelsOff = offNames(panels);
  send({panels: shown ? 'shown' : 'hidden', why, off: panelsOff});
  if (DRY_RUN) return;
  if (!shown) {
    for (const [, w] of panels) hidePanel(main, w);
    return;
  }
  placePanels(laneHeight);
  for (const [name, w] of panels) {
    if (!isOff(name)) msgVoidId(w, sel('orderFront:'), NULL);
  }
}

// Traktor draws its drop-down and context menus (NI::NGL::PopupMenu) inside
// its main window, so they would open under the panels, which are windows of
// their own above it. While one is open (PopupMenu::m_pMasterPopup, the open
// menu, is set; read only), the panels are hidden like for the browser.
const masterPopup = symbol('_ZN2NI3NGL9PopupMenu14m_pMasterPopupE');
let menuWasOpen = false;
function menuOpen() {
  const open = !masterPopup.readPointer().isNull();
  if (open !== menuWasOpen) {
    menuWasOpen = open;
    send({menu: open ? 'open' : 'closed'});
  }
  return open;
}

function syncPanels() {
  if (laneHeight === 0) return;
  const host = laneHost();
  if (host === null) return;
  // Looked up each time: a window kept from an earlier pass may be gone.
  panelWindows = findWindows();
  if (panelWindows === null || panelWindows.panels.length === 0) return;
  const browser = windowTitle(panelWindows.panels[0][1]).endsWith(BROWSER_SUFFIX);
  const laneVisible = hostVisible(host);
  if (laneVisible === null) return;
  const menu = menuOpen();
  const shown = laneVisible && !browser && !menu;
  if (shown !== panelsShown) {
    showPanels(shown, browser ? 'browser' : !laneVisible ? 'not Parallel' : menu ? 'menu' : 'lanes');
  } else if (shown && offNames(panelWindows.panels) !== panelsOff) {
    showPanels(true, 'MIDI');
  } else if (shown && panelsLost() && Date.now() - lastRestore >= RESTORE_MS) {
    // Leaving full screen moves the main window back to its Space, and AppKit
    // leaves the child windows hidden or detached from it.
    lastRestore = Date.now();
    showPanels(true, 'restored');
  } else if (shown && placement(lanePosition(0, laneHeight), laneHeight,
                                contentRect(panelWindows.main), panelWindows.panels) !== placedAt) {
    placePanels(laneHeight);
  }
}

// The panels and the settings button are made by the controller mapping
// that carries them (Controller Manager > Kontrol Z1 MK2). With none of them
// MAPPING_WAIT_MS after Traktor's main window shows, the mapping is missing,
// and wave_height_mac.py says how to add it.
const MAPPING_WAIT_MS = 10000;
let mainShownAt = 0;
let mappingChecked = false;
function checkMapping(found) {
  if (found.panels.length + found.extras.length > 0) {
    mappingChecked = true;
    send({mappingFound: mainShownAt === 0 ? 0 : Date.now() - mainShownAt});
  } else if (mainShownAt === 0) {
    mainShownAt = Date.now();
  } else if (Date.now() - mainShownAt >= MAPPING_WAIT_MS) {
    mappingChecked = true;
    send({noMapping: true});
  }
}

// Shows, places or hides the settings button and window. Needs no lane: the
// header is there in every view. Placed again whenever the main window's
// content moves, or (at most once a second, as for the panels) when one that
// should be seen is hidden or detached, e.g. after leaving full screen.
function syncExtras() {
  const found = findWindows();
  if (found === null) return;
  const {main, extras} = found;
  if (!msgBool(main, sel('isVisible')) || msgBool(main, sel('isMiniaturized'))) return;
  if (!mappingChecked) checkMapping(found);
  const c = contentRect(main);
  const contentTop = c[1] + c[3];
  for (const [name, w] of extras) {
    const kind = name.split(' ')[0];
    let frame = null;
    if (kind === 'button') {
      const top = (HEADER_HEIGHT - BUTTON_SIZE) / 2;
      frame = [c[0] + BUTTON_LEFT, contentTop - top - BUTTON_SIZE, BUTTON_SIZE, BUTTON_SIZE];
    } else if (kind === 'config' && name.endsWith(OPEN_TAG)) {
      const f = msgRect(w, sel('frame'));
      frame = [c[0] + Math.round((c[2] - f[2]) / 2), c[1] + Math.round((c[3] - f[3]) / 2), f[2], f[3]];
    } else if (kind !== 'config') {
      continue;
    }
    const lost = frame !== null && (!msgBool(w, sel('isVisible')) || !msgId(w, sel('parentWindow')).equals(main));
    const key = frame === null ? 'hidden' : frame.join(',');
    const last = extrasPlaced.get(kind);
    if (last !== undefined && last.key === key && !(lost && Date.now() - last.at >= RESTORE_MS)) continue;
    extrasPlaced.set(kind, {key, at: Date.now()});
    if (DRY_RUN) {
      send({dryRunExtra: {kind, frame}});
      continue;
    }
    if (frame === null) {
      hidePanel(main, w);
      continue;
    }
    if (!msgId(w, sel('parentWindow')).equals(main)) msgAddChild(main, sel('addChildWindow:ordered:'), w, NS_WINDOW_ABOVE);
    msgSetFrame(w, sel('setFrame:display:'), frame, 1);
    msgVoidId(w, sel('orderFront:'), NULL);
  }
}

// Whether a panel is hidden or detached while Traktor's main window is on
// screen (not minimised, nor the app hidden, when nothing is to be shown).
function panelsLost() {
  const {main, panels} = panelWindows;
  if (!msgBool(main, sel('isVisible')) || msgBool(main, sel('isMiniaturized'))) return false;
  return panels.some(([name, w]) => !isOff(name)
      && (!msgBool(w, sel('isVisible')) || !msgId(w, sel('parentWindow')).equals(main)));
}

// setInterval runs on Frida's own thread; the check is sent to the main
// queue, at most one at a time.
const dispatchAsync = new NativeFunction(
    Module.getGlobalExportByName('dispatch_async_f'), 'void', ['pointer', 'pointer', 'pointer']);
const mainQueue = Module.getGlobalExportByName('_dispatch_main_q');
let syncQueued = false;
let syncFailed = false;
const syncOnMain = new NativeCallback(() => {
  syncQueued = false;
  if (busy || syncFailed) return;
  try {
    syncExtras();
    syncPanels();
  } catch (e) {
    // Stop polling rather than repeat a failure ten times a second.
    syncFailed = true;
    send({error: 'panel sync stopped: ' + e});
  }
}, 'void', ['pointer']);
setInterval(() => {
  if (syncQueued) return;
  syncQueued = true;
  dispatchAsync(mainQueue, NULL, syncOnMain);
}, POLL_MS);

Interceptor.attach(resizeWaveformAddr, {
  onEnter(args) {
    this.form = busy ? null : args[0];
  },
  onLeave() {
    if (this.form === null) return;
    busy = true;
    try {
      const key = this.form.toString();
      if (isLane(this.form) && !seenLanes.has(key)) {
        seenLanes.add(key);
        hideStemControls(this.form);
      }
      stretchWave(this.form);
      centreControls(this.form);
      if (isLane(this.form)) laneForms.set(this.form.add(FORM_ID).readU32(), this.form);
      if (laneHeight > 0 && isLane(this.form)) placePanels(laneHeight);
    } catch (e) {
      send({error: String(e)});
    } finally {
      busy = false;
    }
  },
});

// Read-only: report the size of each audio ring buffer Traktor creates, so
// the lane one set by `layout_patch.py wave-buffer` can be checked. The
// extra per-stream buffers of 2^15 are left out. Most buffers are created at
// startup, before the script attaches, so existing ones are also reported
// once each from StreamBuffer::lockRefresh (size at STREAM_BUFFER_SIZE, set
// by the constructor). lockRefresh runs on Traktor's streaming thread, so
// that hook is removed after REPORT_MS.
const STREAM_BUFFER_SIZE = 0x80;
const REPORT_MS = 20000;
Interceptor.attach(symbol('_ZN5boost11make_sharedI12StreamBufferJRKjEEENS_6detail15sp_if_not_arrayIT_E4typeEDpOT0_'), {
  onEnter(args) {
    const samples = args[0].readU32();
    if (samples !== 0x8000) send({streamBuffer: samples});
  },
});
const seenBuffers = new Set();
const lockRefresh = Interceptor.attach(symbol('_ZN12StreamBuffer11lockRefreshERjS0_jj'), {
  onEnter(args) {
    const key = args[0].toString();
    if (seenBuffers.has(key)) return;
    seenBuffers.add(key);
    const samples = args[0].add(STREAM_BUFFER_SIZE).readU32();
    if (samples !== 0x8000) send({streamBuffer: samples, existing: true});
  },
});
setTimeout(() => lockRefresh.detach(), REPORT_MS);

send({ready: true, dryRun: DRY_RUN});
