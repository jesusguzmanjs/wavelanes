"""Rewrite the GUI layout XML embedded in a Traktor Pro 4 executable.

The main window layout lives in the exe as an XML resource
(<TraktorGUILayoutPersistence>). A macOS universal binary holds one copy per
architecture, and the arm64 one is packed against the next resource with no
NUL after it, so the span ends at the closing tag. This script replaces every
copy in place: the edited XML is compacted if needed and padded with spaces to
the original length, so no other byte of the executable moves.

Usage (run against a COPY of Traktor, never the original install):
    python -I layout_patch.py extract <exe> <out.xml>
    python -I layout_patch.py apply   <exe> [--lane-height N] [--lanes 3|4]
    python -I layout_patch.py restore <exe>
    python -I layout_patch.py restore-layout <exe>   (only the layout, keeping other patches)
    python -I layout_patch.py install-qml   <exe> [--controller NAME] [--lanes 3|4]
    python -I layout_patch.py uninstall-qml <exe> [--controller NAME]
    python -I layout_patch.py sign <exe>          (macOS only)
    python -I layout_patch.py wave-buffer <exe> N [--write]   (macOS arm64 only)

<exe> is "Traktor Pro 4.exe" on Windows, or "<copy>.app/Contents/MacOS/Traktor Pro 4"
on macOS (the .app path itself is accepted too).

install-qml injects a launcher into one controller's stock mapping
(qml/CSI/<NAME>/<NAME>.qml, default Z1MK2) and copies qml/ next to it, so the
lane panels open when that device is added in the Controller Manager. Pick a
controller you do not own: a real one would run the modified mapping.

On macOS, patching the exe or the QML breaks the code signature; `sign`
re-signs the whole copy, without the hardened runtime and with get-task-allow
so Frida can attach. It signs with the "WaveLanes" code signing identity
from the keychain when there is one (a self-signed certificate is enough):
macOS keys privacy permissions to the signing identity, and an ad hoc
signature's identity changes with every patch, so each re-sign would ask for
them all again. Without it, it falls back to an ad hoc signature. Backups are kept next to the .app, since
any extra file inside the bundle would also break the signature.

wave-buffer sets the lane waveform ring buffer to 2^N samples (Traktor's own
is 2^21, about 47 s at 44.1 kHz; each sample costs 8 bytes, so 16 MB per
buffer at 21). Without --write it only reports what it would change; restore
puts the original back along with the layout.
"""
import hashlib
import re
import plistlib
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# -I (isolated mode) leaves this file's own folder off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_settings  # noqa: E402

MARKER = b"<TraktorGUILayoutPersistence>"
END = b"</TraktorGUILayoutPersistence>\r\n"
QML_DIR = Path(__file__).with_name("qml")
CONTROLLER = "Z1MK2"
SIGNING_IDENTITY = "WaveLanes"

LAUNCHER = """\
  //------------------------------------------------------------------------------------------------------------------
  // WAVELANES: lane panels (one per parallel waveform lane, A to C, or D
  // with four lanes), settings button and window, all from WaveLanes.qml
  // and placed over Traktor by WaveLanes.
  //------------------------------------------------------------------------------------------------------------------

  property var waveLanes: null

  function launchLanePanels() {
    if (waveLanes !== null)
      return
    var component = Qt.createComponent(Qt.resolvedUrl("WaveLanes.qml"))
    if (component.status !== Component.Ready) {
      showLanePanelError(component.errorString())
      return
    }
    waveLanes = component.createObject(null, { lanes: PANEL_COUNT, settingsFile: "SETTINGS_FILE" })
    if (waveLanes === null)
      showLanePanelError(component.errorString() || "WaveLanes.qml: createObject failed")
  }

  // Traktor keeps no log of QML errors, so they are shown in a window.
  function showLanePanelError(message) {
    console.log("[LanePanel] " + message)
    var c = Qt.createComponent(Qt.resolvedUrl("LanePanelError.qml"))
    if (c.status === Component.Ready)
      waveLanes = c.createObject(null, { message: "[LanePanel] " + message })
  }

"""

# What the lane panels show, written by the settings window inside Traktor
# (qml/PanelSettings.qml); its path is built into the injected launcher.
SETTINGS_FILE = ui_settings.UI

# Height in pixels of each parallel waveform lane (Traktor default: 91).
# It must be fixed: MaxY="-2" on a slot means the form's own compiled-in
# height, not the free space, and leaves the rest of the lane black.
# 216 gives the three lanes about half of a 1440 px tall screen.
# The waveform control inside the lane keeps its compiled-in 87 px unless
# wave_height.py is running against Traktor to stretch it to the lane.
LANE_HEIGHT = "216"
LANES = 3


# (scope container, target container, attribute, new value)
# Scope limits the edit to one subtree, since names repeat across views.
# A value of None removes the attribute.
# height None: the lanes share the free height, as the browser does when it
# is there (a minimum and no maximum); used when the browser is hidden. Every
# container between the main slot and the lane loses its maximum too: MaxY="-2"
# keeps a container at its compiled-in size, which left the lanes at 91 px.
# The engine shares the free height evenly between the flexible containers of
# a level, so with three lanes lane C goes into the AB area (lane_moves):
# alone in the CD area it took half the free height.
def lane_area(deck, lanes):
    return "AB" if deck in "AB" or lanes == 3 else "CD"


def lane_edits(height, lanes=LANES):
    if height is None:
        decks = "ABCD"[:lanes]
        edits = [("Main GUI Slot Normal", f"Parallel Wave Area {area}", "MaxY", None)
                 for area in sorted({lane_area(deck, lanes) for deck in decks})]
        for deck in decks:
            area = lane_area(deck, lanes)
            edits += [
                (f"Parallel Wave Area {area}", f"Deck Area {deck}", "MaxY", None),
                (f"Parallel Wave Area {area}", f"Parallel Track {deck}", "MaxY", None),
                (f"Parallel Track {deck}", f"Parallel Wave {deck}", "MinY", "91"),
                (f"Parallel Track {deck}", f"Parallel Wave {deck}", "MaxY", None),
            ]
        if lanes == 3:
            # The engine orders a container's children by Order, not by their
            # place in the XML; lane C's is 0 in the CD area, which put it first.
            edits.append(("Parallel Wave Area AB", "Deck Area C", "Order", "2"))
        return edits
    return [
        (f"Parallel Track {deck}", f"Parallel Wave {deck}", attr, str(height))
        for deck in "ABCD"[:lanes]
        for attr in ("MinY", "MaxY")
    ]


# (scope container, element, scope container, new parent): the element moves
# to the end of the new parent, before the other changes. Only for three lanes
# that share the window's height (see lane_edits); lane_removals then removes
# the CD area left without lanes.
def lane_moves(lanes=LANES, browser=False):
    if browser and lanes == 3:
        return [("Parallel Wave Area CD", "Deck Area C", "Main GUI Slot Normal", "Parallel Wave Area AB")]
    return []


# (scope container, target element) removed with all its children. Shrinking a
# container is not enough: the engine still lays out its children at their
# minimum size, and they spill over the neighbouring areas.
# Only the compact decks Traktor shows under the lanes in the Parallel view
# go; the other views (Essential, Extended, Mixer...) keep their decks, since
# every view is the same layout with containers switched on and off by name.
# With decks=False they stay, and only lane D goes for three lanes.
# With browser=True the browser goes from under the lanes, and the decks from
# over the maximised browser. Unlike the decks, the browser is not one per
# view: it goes from every view, which then only has the maximised one.
def lane_removals(lanes=LANES, decks=True, browser=False):
    removals = []
    if browser:
        removals.append(("Main GUI Slot Normal", "Browser"))
        removals += [("Main GUI Slot Max Browser", area)
                     for area in ("Preparation Deck Area", "Performance Deck Area")]
    if decks:
        removals.append(("Preparation Deck Area", "Deck Parallel Full Area A"))
        removals += [("Performance Deck Area", f"Deck Parallel Full Area {deck}") for deck in "ABCD"]
    if lanes == 3 and browser:
        # Lane C is in the AB area now (lane_moves): the CD area goes whole.
        removals.append(("Main GUI Slot Normal", "Parallel Wave Area CD"))
    elif lanes == 3:
        # Three parallel lanes instead of four; deck D itself still exists.
        removals.append(("Parallel Wave Area CD", "Deck Area D"))
    return removals


EDITS = lane_edits(LANE_HEIGHT)
REMOVALS = lane_removals()

TAG = re.compile(r"<!--.*?-->|<(/?)([A-Za-z]\w*)[^>]*?(/?)>", re.S)


def locate(data):
    """Return the (start, end) span of every embedded layout XML."""
    spans = []
    i = data.find(MARKER)
    while i >= 0:
        start = data.rfind(b"\x00", 0, i) + 1
        if not data.startswith(b"<?xml", start):
            sys.exit(f"Unexpected bytes before layout XML at {start:#x}")
        end = data.find(END, i)
        if end < 0:
            sys.exit(f"Layout XML at {start:#x} has no closing tag")
        spans.append((start, end + len(END)))
        i = data.find(MARKER, end)
    if not spans:
        sys.exit("Layout XML not found; unsupported Traktor build?")
    return spans


def app_bundle(exe):
    """The .app containing exe on macOS, or None on Windows."""
    for p in exe.parents:
        if p.suffix == ".app":
            return p
    return None


def resolve_exe(path):
    if path.suffix == ".app":
        name = plistlib.loads((path / "Contents" / "Info.plist").read_bytes())["CFBundleExecutable"]
        return path / "Contents" / "MacOS" / name
    return path


def backup_dir(exe):
    app = app_bundle(exe)
    return app.parent if app else exe.parent


def backup_name(exe):
    app = app_bundle(exe)
    return f"{app.stem}.{exe.name}" if app else exe.name


def compact(xml):
    xml = re.sub(rb"<!--.*?-->", b"", xml, flags=re.S)
    xml = re.sub(rb">\s+<", b"><", xml)
    return re.sub(rb"[ \t\r\n]+", b" ", xml)


def find_scoped(root, scope, name):
    for s in root.iter():
        if s.get("Name") == scope:
            for t in s.iter():
                if t.get("Name") == name:
                    return t
    return None


def element_span(text, name_pos):
    """Return (start, end) of the element whose start tag contains name_pos."""
    start = text.rindex("<", 0, name_pos)
    depth = 0
    for m in TAG.finditer(text, start):
        if m.group(0).startswith("<!--"):
            continue
        closing, _, selfclosing = m.groups()
        if closing:
            depth -= 1
        elif not selfclosing:
            depth += 1
        if depth == 0:
            return start, m.end()
    sys.exit("Unbalanced layout XML")


def apply_edits(xml, edits=None, removals=None, moves=()):
    # Edit the raw text rather than re-serialising, so formatting the engine
    # might depend on (attribute order, quoting) stays untouched.
    edits = EDITS if edits is None else edits
    removals = REMOVALS if removals is None else removals
    text = xml.decode("utf-8")
    root = ET.fromstring(xml)
    for scope, name, into_scope, into in moves:
        if find_scoped(root, scope, name) is None or find_scoped(root, into_scope, into) is None:
            sys.exit(f"Container not found: {scope} > {name}, or {into_scope} > {into}")
        s = text.index(f'Name="{scope}"')
        start, end = element_span(text, text.index(f'Name="{name}"', s))
        moved = text[start:end]
        text = text[:start] + text[end:]
        s = text.index(f'Name="{into_scope}"')
        _, parent_end = element_span(text, text.index(f'Name="{into}"', s))
        closing = text.rindex("</", 0, parent_end)
        text = text[:closing] + moved + text[closing:]
    root = ET.fromstring(text)
    for scope, name, *_ in edits + removals:
        if find_scoped(root, scope, name) is None:
            sys.exit(f"Container not found: {scope} > {name}")
    for scope, name in removals:
        s = text.index(f'Name="{scope}"')
        start, end = element_span(text, text.index(f'Name="{name}"', s))
        text = text[:start] + text[end:]
    for scope, name, attr, value in edits:
        s = text.index(f'Name="{scope}"')
        t = text.index(f'Name="{name}"', s)
        tag_end = text.index(">", t)
        tag = text[t:tag_end]
        if value is None:
            tag = re.sub(rf'\s+{attr}="[^"]*"', "", tag)
        elif re.search(rf'\b{attr}="[^"]*"', tag):
            tag = re.sub(rf'\b{attr}="[^"]*"', f'{attr}="{value}"', tag)
        else:
            tag += f' {attr}="{value}"'
        text = text[:t] + tag + text[tag_end:]
    out = text.encode("utf-8")
    ET.fromstring(out)
    return out


def inject_launcher(qml, panels=LANES):
    """Add the lane panel launcher, for this many lanes, to a stock controller mapping."""
    m = re.search(r"^Mapping\s*\{[ \t]*\n", qml, re.M)
    if not m:
        sys.exit("No top-level Mapping block in the controller QML")
    launcher = LAUNCHER.replace("PANEL_COUNT", str(panels)).replace("SETTINGS_FILE", SETTINGS_FILE.as_uri())
    qml = qml[:m.end()] + launcher + qml[m.end():]
    handler = re.search(r"^  onMappingLoaded:\s*\{[^}]*?\n(?=\s*\})", qml, re.M)
    if handler:
        qml = qml[:handler.end()] + "    launchLanePanels();\n" + qml[handler.end():]
    else:
        end = qml.rindex("}")
        qml = qml[:end] + "\n  onMappingLoaded: launchLanePanels()\n" + qml[end:]
    if not re.search(r"^import QtQuick ", qml, re.M):
        # Component.Ready needs QtQuick (or QtQml) in scope.
        imp = list(re.finditer(r"^import .*\n", qml, re.M))[-1]
        qml = qml[:imp.end()] + "import QtQuick 2.0\n" + qml[imp.end():]
    return qml


def qml_paths(exe, controller):
    """(controller folder, its mapping, the mapping's stock backup)."""
    app = app_bundle(exe)
    res = app / "Contents" / "Resources" if app else exe.parent / "Resources64"
    folder = res / "qml" / "CSI" / controller
    backup = backup_dir(exe) / f"{backup_name(exe)}.{controller}.qml.lanepanel-backup"
    return folder, folder / f"{controller}.qml", backup


def qml_matches(exe, controller, panels):
    """Whether the QML is installed for this many lane panels (0: only the settings
    button and window; None: not installed at all)."""
    folder, target, backup = qml_paths(exe, controller)
    files = [(f, folder / f.name) for f in QML_DIR.glob("*.qml")]
    if panels is None:
        return not any(dst.exists() for _, dst in files) and (
            not backup.exists() or target.read_bytes() == backup.read_bytes())
    return (backup.exists()
            and target.read_text(encoding="utf-8") == inject_launcher(backup.read_text(encoding="utf-8"), panels)
            and all(dst.exists() and dst.read_bytes() == src.read_bytes() for src, dst in files))


def install_qml(exe, install, controller, panels=LANES):
    folder, target, backup = qml_paths(exe, controller)
    if not target.exists():
        sys.exit(f"No mapping at {target}")
    if not install:
        if not backup.exists():
            sys.exit(f"No backup at {backup}")
        shutil.copy2(backup, target)
        backup.unlink()
        for f in QML_DIR.glob("*.qml"):
            (folder / f.name).unlink(missing_ok=True)
        print("Restored", target)
        return
    if not backup.exists():
        if "launchLanePanels" in target.read_text(encoding="utf-8"):
            # Older installs kept the backup inside the controller folder.
            sys.exit(f"{target} already has the launcher but there is no backup at {backup}; "
                     "move the stock mapping there first")
        shutil.copy2(target, backup)
        print("Backup:", backup)
    # Always inject into the stock mapping, so reinstalling never stacks launchers.
    target.write_text(inject_launcher(backup.read_text(encoding="utf-8"), panels), encoding="utf-8")
    print(f"Injected launcher for {panels} lanes into", target)
    for f in QML_DIR.glob("*.qml"):
        shutil.copy2(f, folder / f.name)
        print("Installed", folder / f.name)


# Lane waveforms are drawn from a ring buffer of audio around the playhead;
# outside it Traktor falls back to the blurry overview. On macOS arm64 the
# size in samples comes from a 3-entry table indexed by stream type, read by
# CachedAudioStream's constructor as
#     adrp x9, table@PAGE; add x9, x9, table@PAGEOFF
#     ldr w24, [x9, w8, sxtw #2]; b 1f; mov w24, #0x400000; 1:
# The third entry, 2^21 (about 47 s at 44.1 kHz), is the lane one. The
# Windows build has it as an immediate instead (see wave_height.js).
WAVE_TABLE_CODE = bytes.fromhex("38d968b8" "02000014" "1808a052")
WAVE_TABLE = (0x20000, 0x8000, 0x200000)
WAVE_ENTRY = 2


def macho_slice(data, cputype):
    """(offset, size) of one architecture in a universal Mach-O."""
    if data[:4] != b"\xca\xfe\xba\xbe":
        sys.exit("Not a universal Mach-O")
    for i in range(int.from_bytes(data[4:8], "big")):
        cpu, _, offset, size, _ = struct.unpack(">5I", data[8 + 20 * i:28 + 20 * i])
        if cpu == cputype:
            return offset, size
    sys.exit("No arm64 slice")


def wave_table(data):
    """File offset of the lane buffer size table in the arm64 slice."""
    base, size = macho_slice(data, 0x0100000C)
    text = data[base:base + size]
    at = text.find(WAVE_TABLE_CODE)
    if at < 0 or text.find(WAVE_TABLE_CODE, at + 1) >= 0:
        sys.exit("Wave buffer code not found exactly once; unsupported Traktor build?")
    adrp, add = struct.unpack("<2I", text[at - 8:at])
    if adrp & 0x9F00001F != 0x90000009 or add & 0xFFC003FF != 0x91000129:
        sys.exit("Unexpected instructions before the wave buffer code")
    # __TEXT starts at file offset 0 of the slice, so VM offset == file offset.
    page = (adrp >> 29 & 3) | (adrp >> 5 & 0x7FFFF) << 2
    page = (page - (1 << 21) if page & 1 << 20 else page) << 12
    return base + ((at - 8) & ~0xFFF) + page + (add >> 10 & 0xFFF)


def wave_buffer_log2(exe):
    """The lane wave buffer size currently in exe, as a power of two."""
    data = exe.read_bytes()
    table = wave_table(data)
    return struct.unpack("<I", data[table + 4 * WAVE_ENTRY:table + 4 * WAVE_ENTRY + 4])[0].bit_length() - 1


def lane_height(exe):
    """The parallel lane height currently in exe's layout, or None if unpatched."""
    data = exe.read_bytes()
    start, end = locate(data)[0]
    lane = find_scoped(ET.fromstring(data[start:end]), "Parallel Track A", "Parallel Wave A")
    value = lane.get("MaxY") if lane is not None else None
    return int(value) if value and value.lstrip("-").isdigit() and int(value) > 0 else None


def wave_buffer(exe, log2, write):
    data = exe.read_bytes()
    table = wave_table(data)
    entries = struct.unpack("<3I", data[table:table + 12])
    current = entries[WAVE_ENTRY]
    if entries[:WAVE_ENTRY] != WAVE_TABLE[:WAVE_ENTRY] or current & (current - 1):
        sys.exit(f"Unexpected wave buffer table {[hex(e) for e in entries]}")
    at = table + 4 * WAVE_ENTRY
    print(f"Lane wave buffer at file offset {at:#x}: 2^{current.bit_length() - 1} samples"
          f" ({data[at:at + 4].hex(' ')})")
    if current == 1 << log2:
        print("Already set; nothing to do")
        return
    new = struct.pack("<I", 1 << log2)
    if not write:
        print(f"Dry run: would write {new.hex(' ')} (2^{log2}); add --write to patch")
        return
    patched = bytearray(data)
    patched[at:at + 4] = new
    exe.write_bytes(patched)
    print(f"Set to 2^{log2} ({new.hex(' ')})")
    if app_bundle(exe):
        print("Signature is now broken; run: layout_patch.py sign", exe)


def signing_identity():
    """SHA-1 of the SIGNING_IDENTITY certificate, or "-" for ad hoc.

    Looked up without -v: a self-signed certificate is reported as untrusted,
    but codesign still signs with it when given its hash.
    """
    out = subprocess.run(["security", "find-identity", "-p", "codesigning"],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(rf'^\s*\d+\) ([0-9A-F]{{40}}) "{re.escape(SIGNING_IDENTITY)}"', out, re.M)
    return m.group(1) if m else "-"


def sign(exe):
    app = app_bundle(exe)
    if not app:
        sys.exit("sign is only needed on macOS")
    if subprocess.run(["pgrep", "-f", str(exe.resolve())], capture_output=True).returncode == 0:
        sys.exit("This copy of Traktor is running; quit it before signing")
    identity = signing_identity()
    out = subprocess.run(["codesign", "-d", "--entitlements", "-", "--xml", str(app)],
                         capture_output=True, check=True).stdout
    ents = plistlib.loads(out) if out.strip() else {}
    ents["com.apple.security.get-task-allow"] = True
    ent_file = backup_dir(exe) / f"{app.stem}.entitlements.plist"
    ent_file.write_bytes(plistlib.dumps(ents))
    # Inner code first: every dylib, bundle and helper must carry the same
    # (ad hoc) identity, or the main exe refuses to load them.
    contents = app / "Contents"
    nested = [p for d in ("Frameworks", "PlugIns") for p in sorted((contents / d).glob("*"))]
    nested += [p for p in sorted((contents / "MacOS").iterdir()) if p != exe]
    for p in nested:
        subprocess.run(["codesign", "--force", "--sign", identity, str(p)], check=True)
    subprocess.run(["codesign", "--force", "--sign", identity, "--entitlements", str(ent_file), str(app)],
                   check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    who = "ad hoc" if identity == "-" else f'as "{SIGNING_IDENTITY}"'
    print(f"Signed {app} {who} ({len(nested)} nested items), entitlements in {ent_file}")


def main():
    controller = CONTROLLER
    height, lanes = LANE_HEIGHT, LANES
    if "--controller" in sys.argv:
        i = sys.argv.index("--controller")
        controller = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    if "--lane-height" in sys.argv:
        i = sys.argv.index("--lane-height")
        height = int(sys.argv[i + 1])
        if height < 91:
            sys.exit("--lane-height must be at least 91 (Traktor's own lane height)")
        del sys.argv[i:i + 2]
    if "--lanes" in sys.argv:
        i = sys.argv.index("--lanes")
        lanes = int(sys.argv[i + 1])
        if lanes not in (3, 4):
            sys.exit("--lanes must be 3 or 4")
        del sys.argv[i:i + 2]
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, exe = sys.argv[1], resolve_exe(Path(sys.argv[2]))
    backup = backup_dir(exe) / f"{backup_name(exe)}.layout-backup"

    if cmd == "sign":
        sign(exe)
        return

    if cmd == "wave-buffer":
        if len(sys.argv) < 4 or not sys.argv[3].isdigit() or not 21 <= int(sys.argv[3]) <= 24:
            sys.exit("wave-buffer takes N between 21 (Traktor's own) and 24")
        wave_buffer(exe, int(sys.argv[3]), "--write" in sys.argv)
        return

    if cmd in ("install-qml", "uninstall-qml"):
        install_qml(exe, cmd == "install-qml", controller, lanes)
        return

    if cmd == "restore":
        if not backup.exists():
            sys.exit(f"No backup at {backup}")
        shutil.copy2(backup, exe)
        print("Restored", exe)
        return

    if cmd == "restore-layout":
        apply_layout(exe, None)
        return

    data = exe.read_bytes()
    spans = locate(data)

    if cmd == "extract":
        start, end = spans[0]
        Path(sys.argv[3]).write_bytes(data[start:end])
        print(f"Wrote {end - start} bytes ({len(spans)} copies in exe)")
        return

    if cmd != "apply":
        sys.exit(__doc__)
    apply_layout(exe, (lane_edits(height, lanes), lane_removals(lanes)))


def layout_target(exe, change):
    """exe's bytes and, per layout copy, (start, the bytes it should hold).

    change is (edits, removals) to patch the pristine layout with, or None
    for the pristine layout itself. The pristine layout comes from the backup
    next to the .app, made on the first patch.
    """
    data = exe.read_bytes()
    spans = locate(data)
    backup = backup_dir(exe) / f"{backup_name(exe)}.layout-backup"
    if not backup.exists():
        if change is not None:
            shutil.copy2(exe, backup)
            print("Backup:", backup)
        orig = data
    else:
        # Always patch from the pristine layout, not a previous patch. A
        # patched copy ends earlier (its padding follows the closing tag),
        # and re-signing changes the file's length, so the copies must
        # start in the same places and the pristine spans are the ones
        # rewritten.
        orig = backup.read_bytes()
        pristine = locate(orig)
        if [s for s, _ in pristine] != [s for s, _ in spans]:
            sys.exit("Backup does not match this exe; delete it if Traktor was updated")
        spans = pristine
    targets = []
    for start, end in spans:
        xml = orig[start:end]
        if change is None:
            targets.append((start, xml))
            continue
        new = apply_edits(xml, *change)
        if len(new) > len(xml):
            new = compact(new)
        if len(new) > len(xml):
            sys.exit(f"Patched layout too large ({len(new)} > {len(xml)})")
        # Trailing spaces after the root element are still well-formed XML.
        targets.append((start, new.ljust(len(xml), b" ")))
    return data, targets


def layout_matches(exe, change):
    data, targets = layout_target(exe, change)
    return all(data[s:s + len(new)] == new for s, new in targets)


def apply_layout(exe, change):
    """Patch every layout copy in exe (see layout_target for change)."""
    data, targets = layout_target(exe, change)
    patched = bytearray(data)
    for start, new in targets:
        patched[start:start + len(new)] = new
    assert len(patched) == len(data)
    exe.write_bytes(patched)
    what = "the pristine layout" if change is None else \
        f"{len(change[0])} attributes, removed {len(change[1])} elements"
    print(f"Patched {len(targets)} copies with {what}; layout sha256 {hashlib.sha256(new).hexdigest()[:12]}")
    if app_bundle(exe):
        print("Signature is now broken; run: layout_patch.py sign", exe)


if __name__ == "__main__":
    main()
