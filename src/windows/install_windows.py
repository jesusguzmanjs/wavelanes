"""Install, update or remove WaveLanes on Windows.

    .venv\\Scripts\\python -I windows\\install_windows.py [--copy PATH]                          # install
    .venv\\Scripts\\python -I windows\\install_windows.py [--copy PATH] --refresh                # make the copy again
    .venv\\Scripts\\python -I windows\\install_windows.py [--copy PATH] --uninstall [--dry-run]

"Install on Windows.bat" and "Uninstall on Windows.bat", at the top of this
repo, make the virtualenv and run this. The Windows counterpart of
mac/install_mac.py.

Install does each step only if it is not done yet:
1. makes the copy of the installed Traktor (ORIGINAL; only read) at PATH
   (default DEFAULT_COPY, in the user's AppData, so neither the copy nor
   applying the layout settings later needs administrator rights). A copy
   older than the installed Traktor is made again, after asking;
2. makes the "WaveLanes" shortcuts, on the desktop and in the Start
   menu, with Traktor's icon. They open Traktor through traktor_config.py
   --launch with pythonw, so without a console window; the output goes to
   LOG, and errors are shown in a message.
The layout and the QML are applied by the shortcut, the first time it opens.

The shortcut also offers to make the copy again when the installed Traktor
is newer than it (traktor_config.py calls offer_refresh). An older one, as
after going back to a previous version, is left alone.

--uninstall deletes the copy (and its backups, which are inside it), the
shortcuts, the settings (ui_settings.UI) and the log, after asking; --dry-run only lists them. Neither the
original Traktor nor Traktor's own settings and collection are touched, nor
this folder.
"""
import ctypes
import functools
import os
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from traktor_config import DEFAULT_COPY, EXE_NAME, fail  # noqa: E402
import ui_settings  # noqa: E402 (traktor_config puts its folder on sys.path)

print = functools.partial(print, flush=True)

ORIGINAL = Path(r"C:\Program Files\Native Instruments\Traktor Pro 4")
DATA = Path(os.environ["LOCALAPPDATA"]) / "WaveLanes"
LOG = DATA / "WaveLanes.log"
SHORTCUT = "WaveLanes.lnk"
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"


def copy_path():
    """The copy's folder, from --copy PATH or DEFAULT_COPY; it need not exist yet."""
    path = DEFAULT_COPY
    if "--copy" in sys.argv:
        i = sys.argv.index("--copy")
        if i + 1 >= len(sys.argv):
            fail("--copy needs the folder of the Traktor copy")
        path = sys.argv[i + 1]
    root = Path(os.path.expandvars(path.strip())).resolve()
    if root == ORIGINAL.resolve():
        fail("The copy cannot be the original Traktor")
    return root


def version(folder):
    """The file version of the folder's Traktor exe, as (4, 5, 1, 34), or None."""
    exe = str(folder / EXE_NAME)
    ver = ctypes.WinDLL("version")
    ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.POINTER(wintypes.UINT)]
    size = ver.GetFileVersionInfoSizeW(exe, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(exe, 0, size, buf):
        return None
    info, length = ctypes.c_void_p(), wintypes.UINT()
    if not ver.VerQueryValueW(buf, "\\", ctypes.byref(info), ctypes.byref(length)):
        return None
    ms, ls = ctypes.cast(info, ctypes.POINTER(wintypes.DWORD))[2:4]  # dwFileVersionMS, LS
    return (ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff)


def shown(v):
    return ".".join(map(str, v[:3])) if v else "?"


def newer_original(copy):
    """(copy's version, installed Traktor's version) if the installed one is newer, else None."""
    a, b = version(copy), version(ORIGINAL)
    return (a, b) if a and b and b > a else None


def traktor_open(copy):
    from wave_height import find_pid
    return find_pid(copy) is not None


def make_copy(copy):
    """Copy the original to copy, through a temporary name, so that a copy cut
    short is never taken for a good one."""
    if not (ORIGINAL / EXE_NAME).exists():
        fail(f"Traktor Pro 4 is not at {ORIGINAL}; install it first")
    copy.parent.mkdir(parents=True, exist_ok=True)
    partial = copy.with_name(f".{copy.name}.partial")
    if partial.exists():
        shutil.rmtree(partial)
    print(f"Copying {ORIGINAL} to {copy} (under a minute)...")
    shutil.copytree(ORIGINAL, partial)
    partial.rename(copy)
    print("Copy made: Traktor", shown(version(copy)))


def refresh_copy(copy):
    """Delete the copy (its backups are inside it) and copy the original again."""
    if copy.exists():
        shutil.rmtree(copy)
    make_copy(copy)


def shortcut_folders():
    """Desktop and Start menu > Programs, wherever Windows has them (OneDrive...)."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "[Environment]::GetFolderPath('Desktop'); [Environment]::GetFolderPath('Programs')"],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    return [Path(p.strip()) for p in out if p.strip()]


def make_shortcut(path, copy):
    args = f'-I "{HERE / "traktor_config.py"}" --launch'
    if copy != Path(os.path.expandvars(DEFAULT_COPY)).resolve():
        args += f' --copy "{copy}"'
    # Values go through the environment, so no quoting reaches PowerShell.
    env = dict(os.environ, TC_LINK=str(path), TC_TARGET=str(PYTHONW), TC_ARGS=args, TC_DIR=str(ROOT),
               TC_ICON=f"{copy / EXE_NAME},0")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TC_LINK); "
                    "$s.TargetPath = $env:TC_TARGET; $s.Arguments = $env:TC_ARGS; "
                    "$s.WorkingDirectory = $env:TC_DIR; $s.IconLocation = $env:TC_ICON; "
                    "$s.Description = 'Traktor with WaveLanes'; $s.Save()"],
                   env=env, check=True)


def ask(question):
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "s", "si", "sí")
    except EOFError:
        return False


def install(copy):
    if traktor_open(copy):
        fail("Close Traktor first")
    print("1/2 Traktor copy")
    if not copy.exists():
        make_copy(copy)
    elif newer := newer_original(copy):
        print(f"  The copy is Traktor {shown(newer[0])}; the installed Traktor is newer, {shown(newer[1])}.")
        if ask("  Make the copy again from the installed Traktor?"):
            refresh_copy(copy)
        else:
            print("  Kept the copy as it is.")
    else:
        print("  Already there:", copy)

    print("2/2 Shortcuts")
    if not PYTHONW.exists():
        fail(f"{PYTHONW} is missing: run Install on Windows.bat, which makes it")
    for folder in shortcut_folders():
        make_shortcut(folder / SHORTCUT, copy)
        print("  ", folder / SHORTCUT)
    print(f"""
Done. Open Traktor with the "WaveLanes" shortcut (desktop or Start
menu). The first time it takes 15-20 s more: it prepares the copy.

Once, in Traktor: Preferences > Controller Manager > Add... > Traktor >
Kontrol Z1 MK2. That turns the panels on. Choose the Parallel view, and for
Hide Track Decks set its decks to Full in Preferences > Layout Manager.""")


def uninstall(copy, dry_run):
    links = [f / SHORTCUT for f in shortcut_folders()]
    targets = [p for p in [copy, *links, ui_settings.UI, LOG] if p.exists()]
    if not targets:
        print("Nothing to remove.")
        return
    print("To remove:")
    for p in targets:
        print("  ", p, "(the Traktor copy, with its backups)" if p == copy
              else "(your WaveLanes settings)" if p == ui_settings.UI else "")
    print(f"Not touched: {ORIGINAL}, Traktor's settings and collection, this folder.")
    if dry_run:
        return
    if traktor_open(copy):
        fail("Close Traktor first")
    if not ask("Remove all of it?"):
        print("Nothing removed.")
        return
    for p in targets:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    if DATA.exists() and not any(DATA.iterdir()):
        DATA.rmdir()
    print("Removed. To remove the rest, delete this folder.")


def main():
    copy = copy_path()
    if "--uninstall" in sys.argv:
        uninstall(copy, "--dry-run" in sys.argv)
    elif "--refresh" in sys.argv:
        if traktor_open(copy):
            fail("Close Traktor first")
        refresh_copy(copy)
    else:
        install(copy)


if __name__ == "__main__":
    main()
