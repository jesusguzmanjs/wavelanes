"""Install, update or remove WaveLanes on macOS.

    .venv/bin/python -I mac/install_mac.py [--copy PATH]                         # install
    .venv/bin/python -I mac/install_mac.py [--copy PATH] --refresh               # make the copy again
    .venv/bin/python -I mac/install_mac.py [--copy PATH] --newer                 # exit 10 if Traktor was updated
    .venv/bin/python -I mac/install_mac.py [--copy PATH] --uninstall [--dry-run]

"Install on Mac.command" and "Uninstall on Mac.command", at the top of this
repo, make the virtualenv and run this; WaveLanes.app runs it with
--refresh when Traktor has been updated.

Install does each step only if it is not done yet:
1. makes the copy of /Applications/Traktor Pro 4.app at PATH (default
   /Applications/Traktor Pro 4 WaveLanes.app); the original is only read. A copy
   older than the installed Traktor is made again, after asking;
2. creates the "WaveLanes" code signing identity in the login keychain
   (self-signed; layout_patch.sign uses it, so macOS keeps the copy's privacy
   permissions across patches);
3. builds WaveLanes.app next to the copy (make_launcher_mac.py) and shows
   it in Finder.
The layout and the QML are applied by the launcher, the first time it opens.

--refresh deletes the copy and its backups and makes the copy again: what
WaveLanes.app does, after asking, when --newer finds the installed
Traktor newer than the copy (it prints "old → new"). An older one, as after
going back to a previous version, is left alone.

--uninstall deletes the copy, its backups, WaveLanes.app, the signing
identity, the settings (ui_settings.UI) and the launcher's log, after asking; --dry-run only lists them.
Neither the original Traktor nor Traktor's own settings and collection are
touched.
"""
import functools
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traktor_config import DEFAULT_COPY, ROOT, fail, traktor_running  # noqa: E402

sys.path.insert(0, str(ROOT))
import layout_patch  # noqa: E402
import ui_settings  # noqa: E402

print = functools.partial(print, flush=True)

ORIGINAL = Path("/Applications/Traktor Pro 4.app")
EXE_NAME = "Traktor Pro 4"
LOG = Path.home() / "Library" / "Logs" / "WaveLanes.log"


def copy_path():
    """The copy's .app, from --copy PATH or DEFAULT_COPY; it need not exist yet."""
    path = DEFAULT_COPY
    if "--copy" in sys.argv:
        i = sys.argv.index("--copy")
        if i + 1 >= len(sys.argv):
            fail("--copy needs the path of the Traktor copy")
        path = sys.argv[i + 1]
    if not path.endswith(".app"):
        fail(f"The Traktor copy must be the path of a .app, not {path!r}")
    app = Path(path).expanduser().resolve()
    if app == ORIGINAL.resolve():
        fail("The copy cannot be the original Traktor")
    return app


def version(app):
    """The app's version, as '4.5.0 7', or None without one."""
    try:
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    except OSError:
        return None
    return info.get("CFBundleShortVersionString")


def newer(a, b):
    """Whether version a is newer than version b."""
    def key(v):
        return [int(n) for n in re.findall(r"\d+", v or "")]
    return key(a) > key(b)


def launcher(copy):
    return copy.parent / "WaveLanes.app"


def backups(copy):
    """The copy's backups, kept next to it by layout_patch."""
    exe = copy / "Contents" / "MacOS" / EXE_NAME
    folder, name = layout_patch.backup_dir(exe), layout_patch.backup_name(exe)
    found = [folder / f"{name}.layout-backup", folder / f"{copy.stem}.entitlements.plist"]
    found += sorted(folder.glob(f"{name}.*.qml.lanepanel-backup"))
    return [p for p in found if p.exists()]


def ask(question):
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "s", "si", "sí")
    except EOFError:
        return False


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def check_closed(copy):
    for app in (ORIGINAL, copy):
        if traktor_running(app / "Contents" / "MacOS" / EXE_NAME):
            fail(f"Quit Traktor first ({app.name} is open)")


def make_copy(copy):
    """Copy the original to copy, through a temporary name, so that a copy cut
    short is never taken for a good one."""
    if not ORIGINAL.exists():
        fail(f"Traktor Pro 4 is not at {ORIGINAL}; install it first")
    copy.parent.mkdir(parents=True, exist_ok=True)
    partial = copy.with_name(f".{copy.name}.partial")
    if partial.exists():
        shutil.rmtree(partial)
    print(f"Copying {ORIGINAL.name} to {copy} (a minute or so)...")
    subprocess.run(["ditto", str(ORIGINAL), str(partial)], check=True)
    partial.rename(copy)
    print("Copy made:", version(copy))


def refresh_copy(copy):
    """Delete the copy and its backups and copy the original again."""
    for p in backups(copy):
        remove(p)
    if copy.exists():
        shutil.rmtree(copy)
    make_copy(copy)


def has_identity():
    return layout_patch.signing_identity() != "-"


def create_identity():
    """A self-signed code signing certificate, "WaveLanes", in the login
    keychain, made with macOS's own openssl (LibreSSL), whose .p12 the
    keychain accepts as is."""
    config = f"""\
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = {layout_patch.SIGNING_IDENTITY}
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
"""
    openssl = "/usr/bin/openssl"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "cs.cnf").write_text(config)
        password = subprocess.run([openssl, "rand", "-hex", "16"], capture_output=True, text=True,
                                  check=True).stdout.strip()
        quiet = {"capture_output": True, "check": True}
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                        "-config", str(d / "cs.cnf"), "-keyout", str(d / "key.pem"), "-out", str(d / "cert.pem")],
                       **quiet)
        subprocess.run([openssl, "pkcs12", "-export", "-inkey", str(d / "key.pem"), "-in", str(d / "cert.pem"),
                        "-name", layout_patch.SIGNING_IDENTITY, "-out", str(d / "id.p12"),
                        "-passout", f"pass:{password}"], **quiet)
        keychain = Path.home() / "Library" / "Keychains" / "login.keychain-db"
        subprocess.run(["security", "import", str(d / "id.p12"), "-k", str(keychain), "-P", password,
                        "-T", "/usr/bin/codesign"], **quiet)
    if not has_identity():
        fail("The signing certificate was made but the keychain does not list it")


def install(copy):
    check_closed(copy)
    print("1/3 Traktor copy")
    if not copy.exists():
        make_copy(copy)
    elif ORIGINAL.exists() and newer(version(ORIGINAL), version(copy)):
        print(f"  The copy is Traktor {version(copy)}; the installed Traktor is newer, {version(ORIGINAL)}.")
        if ask("  Make the copy again from the installed Traktor?"):
            refresh_copy(copy)
        else:
            print("  Kept the copy as it is.")
    else:
        print("  Already there:", copy)

    print(f'2/3 Signing certificate "{layout_patch.SIGNING_IDENTITY}"')
    if has_identity():
        print("  Already in the keychain")
    else:
        print("  Creating it (macOS may ask for your login password)...")
        create_identity()
        print("  Created")

    print("3/3 WaveLanes.app")
    subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("make_launcher_mac.py")),
                    "--copy", str(copy)], check=True)
    subprocess.run(["open", "-R", str(launcher(copy))])
    print(f"""
Done. WaveLanes.app is next to the copy, in {copy.parent}
(Finder shows it; drag it to the Dock if you like). Always open Traktor with it.

Once, in Traktor: Preferences > Controller Manager > Add... > Traktor >
Kontrol Z1 MK2. That turns the panels on. For Hide Track Decks, also set the
decks to Full in Preferences > Layout Manager (Parallel layout).""")


def uninstall(copy, dry_run):
    targets = [p for p in [copy, *backups(copy), launcher(copy), ui_settings.UI, LOG] if p.exists()]
    identity = layout_patch.signing_identity()
    identity = None if identity == "-" else identity
    if not targets and not identity:
        print("Nothing to remove.")
        return
    print("To remove:")
    for p in targets:
        print("  ", p, "(your WaveLanes settings)" if p == ui_settings.UI else "")
    if identity:
        print(f'   the signing certificate "{layout_patch.SIGNING_IDENTITY}" (login keychain)')
    print(f"Not touched: {ORIGINAL}, Traktor's settings and collection, this folder.")
    if dry_run:
        return
    check_closed(copy)
    if not ask("Remove all of it?"):
        print("Nothing removed.")
        return
    for p in targets:
        remove(p)
    if ui_settings.DATA.exists() and not any(ui_settings.DATA.iterdir()):
        ui_settings.DATA.rmdir()
    if identity:
        subprocess.run(["security", "delete-identity", "-Z", identity], capture_output=True)
    print("Removed. To remove the rest, delete this folder.")


def main():
    copy = copy_path()
    if "--uninstall" in sys.argv:
        uninstall(copy, "--dry-run" in sys.argv)
    elif "--newer" in sys.argv:
        if copy.exists() and ORIGINAL.exists() and newer(version(ORIGINAL), version(copy)):
            print(f"{version(copy)} → {version(ORIGINAL)}")
            sys.exit(10)
    elif "--refresh" in sys.argv:
        check_closed(copy)
        refresh_copy(copy)
    else:
        install(copy)


if __name__ == "__main__":
    main()
