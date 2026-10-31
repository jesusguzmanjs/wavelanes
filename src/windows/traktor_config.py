"""Apply the layout settings to the Traktor copy, then launch it.

    .venv\\Scripts\\python -I windows\\traktor_config.py [--copy PATH]            # apply
    .venv\\Scripts\\python -I windows\\traktor_config.py [--copy PATH] --check    # only report; exit 3 if something would change
    .venv\\Scripts\\python -I windows\\traktor_config.py [--copy PATH] --launch   # apply, then open Traktor (WaveLanes.bat)
    .venv\\Scripts\\pythonw -I windows\\traktor_config.py [--copy PATH] --launch  # the same, no console (the shortcut)

The Windows counterpart of mac/traktor_config.py. PATH is the folder of the
Traktor copy (default DEFAULT_COPY). The settings are the layout ones of the
settings window inside Traktor, kept in settings.json (ui_settings.py):
    hideDecks    true: the Parallel view has no track decks, only the lanes
    lanes        3 or 4 parallel lanes; with three, lane D goes (deck D stays)
    laneHeight   lane height in pixels, at least 91 (Traktor's own)
    waveBuffer   lane waveform ring buffer, 2^N samples, 21 (Traktor's own) to 24

The layout lives in the executable and the QML (lane panels, settings button
and window, installed either way) in the copy, so changing them needs Traktor
closed. A copy in the user's AppData (DEFAULT_COPY, made by install_windows.py)
is changed as is; one under Program Files needs administrator rights, which
the script asks for (UAC) only when something has to change. The wave buffer is not
patched into the executable on Windows: wave_height.py sets it when it
launches Traktor. What the copy then holds is recorded in
settings.json, for the window to tell what waits for a restart.
Errors exit 1 with a one-line reason.

With pythonw (no console: the shortcut install_windows.py makes) the output
goes to LOG and errors are also shown in a message. --launch opens Traktor
only once: a second launch while the first is still attached just exits.
Before applying anything, --launch offers to make the copy again when the
installed Traktor is newer than it (install_windows.py).
"""
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# -I (isolated mode) leaves the script's own folder off sys.path.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import layout_patch  # noqa: E402
import ui_settings  # noqa: E402

APPLY_LOG = ROOT / "wavelanes-apply.log"
EXE_NAME = "Traktor Pro 4.exe"
DEFAULT_COPY = r"%LOCALAPPDATA%\WaveLanes\Traktor Pro 4 WaveLanes"
LOG = Path(os.environ["LOCALAPPDATA"]) / "WaveLanes" / "WaveLanes.log"
# pythonw has no console: sys.stdout is None until main() points it at LOG.
NO_CONSOLE = sys.stdout is None
MB_YESNO, MB_ICONERROR, MB_ICONQUESTION, MB_ICONINFORMATION = 4, 0x10, 0x20, 0x40
MB_SETFOREGROUND, IDYES = 0x10000, 6


def message(text, flags=MB_ICONINFORMATION):
    """A Windows message box titled WaveLanes; returns the button pressed."""
    return ctypes.windll.user32.MessageBoxW(None, text, "WaveLanes", flags | MB_SETFOREGROUND)


def fail(reason):
    print(reason, file=sys.stderr)
    if NO_CONSOLE:
        message(reason, MB_ICONERROR)
    sys.exit(1)


def copy_path():
    """The copy's folder, from --copy PATH or DEFAULT_COPY."""
    path = DEFAULT_COPY
    if "--copy" in sys.argv:
        i = sys.argv.index("--copy")
        if i + 1 >= len(sys.argv):
            fail("--copy needs the folder of the Traktor copy")
        path = sys.argv[i + 1]
    root = Path(os.path.expandvars(path.strip())).resolve()
    if not (root / EXE_NAME).exists():
        fail(f"No Traktor copy at {root} (give it with --copy)")
    return root


def load():
    """The layout settings, checked."""
    try:
        return ui_settings.layout()
    except ui_settings.SettingsError as e:
        fail(str(e))


def layout_change(p):
    """(edits, removals) for the layout, or None for Traktor's own."""
    edits = [] if p["laneHeight"] == 91 else layout_patch.lane_edits(p["laneHeight"], p["lanes"])
    removals = layout_patch.lane_removals(p["lanes"], decks=p["hideDecks"])
    return (edits, removals) if edits or removals else None


def panels(p):
    """Lane panels to create."""
    return p["lanes"]


def pending(p, exe):
    changes = []
    if not layout_patch.layout_matches(exe, layout_change(p)):
        changes.append("layout")
    if not layout_patch.qml_matches(exe, layout_patch.CONTROLLER, panels(p)):
        changes.append("QML")
    return changes


def apply(p, exe):
    if not layout_patch.layout_matches(exe, layout_change(p)):
        layout_patch.apply_layout(exe, layout_change(p))
    if not layout_patch.qml_matches(exe, layout_patch.CONTROLLER, panels(p)):
        layout_patch.install_qml(exe, True, layout_patch.CONTROLLER, panels(p))


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def writable(root):
    """Whether this user can change the copy without administrator rights (a
    copy in the user's own folders, not under Program Files)."""
    probe = root / ".wavelanes-write-test"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        (root / EXE_NAME).open("r+b").close()
        return True
    except OSError:
        return False


def apply_elevated(root):
    """Run this script with --apply-elevated as administrator, and wait for it."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    APPLY_LOG.unlink(missing_ok=True)
    info = SHELLEXECUTEINFOW(
        cbSize=ctypes.sizeof(SHELLEXECUTEINFOW),
        fMask=0x40,  # SEE_MASK_NOCLOSEPROCESS
        lpVerb="runas",
        lpFile=sys.executable,
        lpParameters=f'-I "{Path(__file__).resolve()}" --apply-elevated --copy "{root}"',
        nShow=0,     # SW_HIDE
    )
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        fail("Administrator rights were not granted; the settings were not applied")
    kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    if APPLY_LOG.exists():
        print(APPLY_LOG.read_text(encoding="utf-8"), end="")
        APPLY_LOG.unlink()
    if code.value:
        fail("Applying the settings as administrator failed")


def single_launch():
    """Whether this is the only launcher running; the mutex lives as long as
    the process, so the next one can tell."""
    global _mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _mutex = kernel32.CreateMutexW(None, False, "Local\\WaveLanesLauncher")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def offer_refresh(root):
    """Offer to make the copy again when the installed Traktor is newer."""
    import install_windows
    found = install_windows.newer_original(root)
    if found is None or not writable(root.parent):
        return
    question = (f"Traktor {install_windows.shown(found[1])} is installed, newer than the copy WaveLanes "
                f"uses ({install_windows.shown(found[0])}). Make the copy again from it? It takes under a "
                "minute; your settings and collection are not touched.")
    if NO_CONSOLE:
        yes = message(question, MB_YESNO | MB_ICONQUESTION) == IDYES
    else:
        yes = install_windows.ask(question)
    if yes:
        install_windows.refresh_copy(root)


def main():
    if "--apply-elevated" in sys.argv:
        # Started hidden by apply_elevated; the output goes back through a file.
        sys.stdout = sys.stderr = open(APPLY_LOG, "w", encoding="utf-8")
        apply(load(), copy_path() / EXE_NAME)
        return
    # Before touching the log: a second launch must not truncate the one the
    # first is still writing.
    if "--launch" in sys.argv and not single_launch():
        print("WaveLanes is already running")
        return
    if NO_CONSOLE:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(LOG, "w", encoding="utf-8", buffering=1)

    p = load()
    root = copy_path()
    exe = root / EXE_NAME
    from wave_height import find_pid
    if "--launch" in sys.argv and find_pid(root) is None:
        offer_refresh(root)
    changes = pending(p, exe)
    if not changes:
        print("Copy matches the settings")
    else:
        print("Pending:", "; ".join(changes))
        if "--check" in sys.argv:
            sys.exit(3)
        if find_pid(root) is not None:
            fail(f"Close Traktor to apply the settings ({'; '.join(changes)})")
        if ctypes.windll.shell32.IsUserAnAdmin() or writable(root):
            apply(p, exe)
        else:
            apply_elevated(root)
        if pending(p, exe):
            fail(f"The settings did not apply: {'; '.join(pending(p, exe))}")
        print("Applied the settings")
    if "--check" in sys.argv:
        return
    # The wave buffer is set as Traktor launches, so it counts as applied
    # along with the rest, as long as Traktor is not already running.
    if find_pid(root) is None:
        ui_settings.set_applied(p)

    if "--launch" not in sys.argv:
        return
    import wave_height
    sys.argv = [sys.argv[0], str(root), "--launch", "--wave-buffer", str(p["waveBuffer"])]
    try:
        wave_height.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Without a console nobody would see the traceback: it goes to LOG.
        import traceback
        traceback.print_exc()
        if NO_CONSOLE:
            message(f"WaveLanes stopped with an error. The details are in {LOG}", MB_ICONERROR)
        sys.exit(1)
