"""Apply the layout settings to the Traktor copy before it starts.

    .venv/bin/python -I mac/traktor_config.py [--copy PATH]           # apply, re-sign if needed
    .venv/bin/python -I mac/traktor_config.py [--copy PATH] --check   # only report; exit 3 if something would change

PATH is the Traktor copy (default DEFAULT_COPY); WaveLanes.app passes
the one it was built for. The settings are the layout ones of the settings
window inside Traktor, kept in settings.json (ui_settings.py):
    hideDecks    true: the Parallel view has no track decks, only the lanes
    hideBrowser  true: no browser under the lanes (in any view), and no decks
                 over the maximised one
    lanes        3 or 4 parallel lanes; with three, lane D goes (deck D stays)
    laneHeight   lane height in pixels, at least 91 (Traktor's own)
    waveBuffer   lane waveform ring buffer, 2^N samples, 21 (Traktor's own) to 24
They only depend on each other for room on the screen.

The layout and the buffer live in the executable and the QML in the app, so
they can only change while Traktor is closed, and the copy is re-signed
afterwards (with the same identity, so macOS asks for no permissions again).
The QML (lane panels, settings button and window) is installed either way.
Run by WaveLanes.app on every launch; when the copy already matches, it
changes nothing and returns at once. What the copy then holds is recorded in
settings.json, for the window to tell what waits for a restart.
Errors exit 1 with a one-line reason, which the launcher shows.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import layout_patch  # noqa: E402
import ui_settings  # noqa: E402

DEFAULT_COPY = "/Applications/Traktor Pro 4 WaveLanes.app"


def fail(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)


def copy_paths():
    """(the copy's .app, its executable), from --copy PATH or DEFAULT_COPY."""
    path = DEFAULT_COPY
    if "--copy" in sys.argv:
        i = sys.argv.index("--copy")
        if i + 1 >= len(sys.argv):
            fail("--copy needs the path of the Traktor copy")
        path = sys.argv[i + 1]
    if not path.endswith(".app"):
        fail(f"The Traktor copy must be the path of a .app, not {path!r}")
    app = Path(path).expanduser().resolve()
    exe = app / "Contents" / "MacOS" / "Traktor Pro 4"
    if not exe.exists():
        fail(f"No Traktor copy at {app} (give it with --copy)")
    return app, exe


def load():
    """The layout settings, checked."""
    try:
        return ui_settings.layout()
    except ui_settings.SettingsError as e:
        fail(str(e))


def layout_change(p):
    """(edits, removals) for the layout, or None for Traktor's own."""
    if p["hideBrowser"]:
        # No browser to take the free height: the lanes share it.
        edits = layout_patch.lane_edits(None, p["lanes"])
    else:
        edits = [] if p["laneHeight"] == 91 else layout_patch.lane_edits(p["laneHeight"], p["lanes"])
    removals = layout_patch.lane_removals(p["lanes"], decks=p["hideDecks"], browser=p["hideBrowser"])
    moves = layout_patch.lane_moves(p["lanes"], browser=p["hideBrowser"])
    return (edits, removals, moves) if edits or removals else None


def panels(p):
    """Lane panels to create."""
    return p["lanes"]


def pending(p, exe):
    changes = []
    if not layout_patch.layout_matches(exe, layout_change(p)):
        changes.append("layout")
    if layout_patch.wave_buffer_log2(exe) != p["waveBuffer"]:
        changes.append(f"waveBuffer {layout_patch.wave_buffer_log2(exe)} -> {p['waveBuffer']}")
    if not layout_patch.qml_matches(exe, layout_patch.CONTROLLER, panels(p)):
        changes.append("QML")
    return changes


def traktor_running(exe):
    return subprocess.run(["pgrep", "-f", str(exe)], capture_output=True).returncode == 0


def main():
    p = load()
    exe = copy_paths()[1]
    changes = pending(p, exe)
    if not changes:
        print("Copy matches the settings")
        if "--check" not in sys.argv and not traktor_running(exe):
            ui_settings.set_applied(p)
        return
    print("Pending:", "; ".join(changes))
    if "--check" in sys.argv:
        sys.exit(3)
    if traktor_running(exe):
        fail(f"Quit Traktor to apply the settings ({'; '.join(changes)})")
    if not layout_patch.layout_matches(exe, layout_change(p)):
        layout_patch.apply_layout(exe, layout_change(p))
    if layout_patch.wave_buffer_log2(exe) != p["waveBuffer"]:
        layout_patch.wave_buffer(exe, p["waveBuffer"], write=True)
    if not layout_patch.qml_matches(exe, layout_patch.CONTROLLER, panels(p)):
        layout_patch.install_qml(exe, True, layout_patch.CONTROLLER, panels(p))
    layout_patch.sign(exe)
    if pending(p, exe):
        fail(f"The settings did not apply: {'; '.join(pending(p, exe))}")
    ui_settings.set_applied(p)


if __name__ == "__main__":
    main()
