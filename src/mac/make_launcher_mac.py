"""Build "WaveLanes.app", the macOS counterpart of WaveLanes.bat.

    .venv/bin/python -I mac/make_launcher_mac.py [--copy PATH]

PATH is the Traktor copy (default /Applications/Traktor Pro 4 WaveLanes.app); the
app is written next to it, and has it built in. Double-clicking it first
offers to make the copy again if /Applications/Traktor Pro 4.app is newer
than it (install_mac.py --newer, then --refresh), then applies the layout
settings of the settings window (traktor_config.py: layout, lane panels and
wave buffer, which live in the app, so the copy is patched and re-signed when
they change), then opens the copy the usual way (with `open`, so macOS keeps
treating it as the same app and its privacy permissions stay; with the two
variables that let the settings window keep its file), and runs
wave_height_mac.py --apply --early in the background, with no Dock icon, until Traktor quits. Its output goes to
~/Library/Logs/WaveLanes.log. A bad setting, or a changed one while
Traktor is open, is shown in an alert. If the script is already attached, the
app only opens Traktor.

The app runs this repo's scripts and .venv in place, and has the copy's path
built in, so rebuild it if either moves. It is not signed; it is a shell script, which macOS runs as is.
"""
import os
import plistlib
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traktor_config import ROOT, copy_paths  # noqa: E402

HERE = Path(__file__).resolve().parent
COPY = copy_paths()[0]  # from --copy, or the default
APP = COPY.parent / "WaveLanes.app"
NAME = "WaveLanes"

LAUNCHER = """\
#!/bin/sh
# Apply the layout settings, open the patched Traktor copy and keep
# wave_height_mac.js attached to it.
COPY={copy}
ROOT={root}
TOOLS={tools}
PY="$ROOT/.venv/bin/python"
LOG="$HOME/Library/Logs/WaveLanes.log"
ICON="$(dirname "$0")/../Resources/Traktor.icns"

# The settings window (qml/PanelSettings.qml) reads and writes its JSON file
# from QML, which Qt allows for local files only with these set.
open_copy() {{
    open --env QML_XHR_ALLOW_FILE_READ=1 --env QML_XHR_ALLOW_FILE_WRITE=1 "$COPY"
}}

# A message with Traktor's icon; ask() returns the button clicked.
ask() {{
    message=$1
    shift
    osascript -e 'on run argv' \\
        -e 'set b to {{}}' -e 'repeat with i from 3 to count argv' -e 'set end of b to item i of argv' -e 'end repeat' \\
        -e 'button returned of (display dialog (item 1 of argv) with title "WaveLanes" buttons b default button (count b) with icon (POSIX file (item 2 of argv) as alias))' \\
        -e 'end run' "$message" "$ICON" "$@"
}}

alert() {{
    ask "$1" OK >/dev/null
}}

# Traktor updated since the copy was made: the patches were made for the old
# version, so offer to copy it again (Traktor's settings and collection stay).
update_copy() {{
    change=$("$PY" -I "$TOOLS/install_mac.py" --copy "$COPY" --newer)
    [ $? -eq 10 ] || return 0
    answer=$(ask "Traktor has been updated ($change). Update the WaveLanes copy now? It takes a minute; your settings and collection are kept." "Not Now" Update)
    [ "$answer" = "Update" ] || return 0
    osascript -e 'display notification "Copying Traktor, a minute or so…" with title "WaveLanes"'
    if ! "$PY" -I "$TOOLS/install_mac.py" --copy "$COPY" --refresh >>"$LOG" 2>&1; then
        alert "The copy could not be updated: $(tail -1 "$LOG")"
        exit 1
    fi
}}

if pgrep -f "$COPY/Contents/MacOS/" >/dev/null; then
    # Traktor is open: the layout cannot change now.
    if ! out=$("$PY" -I "$TOOLS/traktor_config.py" --copy "$COPY" --check 2>&1); then
        alert "Quit Traktor to apply the Layout settings: $(echo "$out" | tail -1)"
        open_copy
        exit 0
    fi
    if pgrep -f "wave_height_mac.py --apply" >/dev/null; then
        open_copy
        exit 0
    fi
else
    : >"$LOG"
    update_copy
    if ! out=$("$PY" -I "$TOOLS/traktor_config.py" --copy "$COPY" 2>&1); then
        echo "$out" >>"$LOG"
        alert "$(echo "$out" | tail -1)"
        exit 1
    fi
    echo "$out" >>"$LOG"
fi
# Start waiting before Traktor starts, so the script sees its first layout.
"$PY" -I "$TOOLS/wave_height_mac.py" --copy "$COPY" --apply --early >>"$LOG" 2>&1 &
open_copy
wait
"""


def main():
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        sys.exit(f"No virtualenv at {python.parent.parent}")
    if APP.exists():
        shutil.rmtree(APP)
    macos = APP / "Contents" / "MacOS"
    resources = APP / "Contents" / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir()
    exe = macos / NAME
    exe.write_text(LAUNCHER.format(copy=shlex.quote(str(COPY)), root=shlex.quote(str(ROOT)), tools=shlex.quote(str(HERE))))
    os.chmod(exe, 0o755)
    shutil.copy2(COPY / "Contents" / "Resources" / "Traktor.icns", resources / "Traktor.icns")
    info = {
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": "local.wavelanes.launcher",
        "CFBundleExecutable": NAME,
        "CFBundleIconFile": "Traktor.icns",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSUIElement": True,
    }
    (APP / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    print("Built", APP)


if __name__ == "__main__":
    main()
