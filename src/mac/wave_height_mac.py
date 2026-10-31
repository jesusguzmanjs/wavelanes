"""Run wave_height_mac.js against the running Traktor copy on macOS.

    .venv/bin/python -I mac/wave_height_mac.py [--copy PATH]          # dry run: report, change nothing
    .venv/bin/python -I mac/wave_height_mac.py [--copy PATH] --apply  # stretch the lane waveforms
    .venv/bin/python -I mac/wave_height_mac.py --copy PATH --apply --early   # used by the launcher

Waits for Traktor to start if it is not running yet, then stays attached until
Traktor quits. It never detaches on its own: unloading the Frida agent from a
running Traktor crashed it once (a signal reached a handler in the freed
agent), so to load a new version of the script, quit Traktor and run this
again. Ctrl+C is ignored while attached; quit Traktor instead.

Only the Traktor copy at PATH (default /Applications/Traktor Pro 4 WaveLanes.app)
is attached to, never another Traktor install.

--early attaches as soon as the copy's process appears, instead of giving it
10 s to build its main window, so the hooks see the first lane layout and no
window resize is needed. make_launcher_mac.py builds an app that opens the
copy and runs this with --apply --early.
"""
import functools
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import frida

# -I (isolated mode) leaves the script's own folder off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import traktor_config  # noqa: E402
from traktor_config import copy_paths  # noqa: E402

print = functools.partial(print, flush=True)

COPY, EXE = copy_paths()
JS = Path(__file__).with_name("wave_height_mac.js")
NO_MAPPING = ("The WaveLanes panels have not appeared. If this is the first time, add the "
              "mapping that carries them, once: Preferences > Controller Manager > Add... > Traktor > "
              "Kontrol Z1 MK2.")


def find_pid():
    for p in frida.get_local_device().enumerate_processes(scope="full"):
        path = p.parameters.get("path")
        if p.name == EXE.name and path and Path(path).resolve() == EXE:
            return p.pid
    return None


def attach(early):
    waiting = False
    while True:
        pid = find_pid()
        if pid is None:
            if not waiting:
                print(f"Waiting for {COPY.name} to start...")
                waiting = True
            time.sleep(0.1 if early else 1)
            continue
        if waiting and not early:
            # Let the main window and its lanes be built before hooking.
            time.sleep(10)
        try:
            return frida.attach(pid)
        except (frida.ProcessNotRespondingError, frida.TransportError, frida.NotSupportedError) as e:
            # Still starting up; try again shortly.
            print("Attach failed, retrying:", e)
            time.sleep(0.5)
        except frida.ProcessNotFoundError:
            pass


def main():
    apply = "--apply" in sys.argv
    source = JS.read_text(encoding="utf-8")
    flag = "const DRY_RUN = true;"
    if flag not in source:
        sys.exit(f"{flag!r} not found in {JS.name}")
    if apply:
        source = source.replace(flag, "const DRY_RUN = false;")

    session = attach("--early" in sys.argv)
    done = threading.Event()
    session.on("detached", lambda reason, crash: (print("Detached:", reason), done.set()))

    def on_message(message, _):
        if message["type"] == "error":
            print("Script error:", message.get("stack") or message.get("description"))
            return
        p = message["payload"]
        if "ready" in p:
            print("Hooked;", "dry run, nothing will be changed" if p["dryRun"] else "stretching waveforms")
        elif "mappingFound" in p:
            print(f"  panels made {p['mappingFound'] / 1000:.1f} s after the main window showed")
        elif "noMapping" in p:
            print("No panels: the Kontrol Z1 MK2 mapping is missing from the Controller Manager")
            # Not waited for: the messages keep coming while it is open.
            subprocess.Popen(["osascript", "-e", "on run argv", "-e",
                              'display dialog (item 1 of argv) with title "WaveLanes" buttons {"OK"} '
                              'default button 1 with icon (POSIX file (item 2 of argv) as alias)', "-e", "end run",
                              NO_MAPPING, str(COPY / "Contents" / "Resources" / "Traktor.icns")],
                             stdout=subprocess.DEVNULL)
        elif "dryRun" in p:
            d = p["dryRun"]
            print(f"  would set lane {d['id']} wave rect {d['rect']} -> {d['newRect']}")
        elif "dryRunHide" in p:
            d = p["dryRunHide"]
            print(f"  would hide Traktor's stem controls (StemControls {d['stems']}, from {d['where']},"
                  f" shown byte {d['shown']} -> 0)")
        elif "dryRunPanel" in p:
            d = p["dryRunPanel"]
            print(f"  would {'attach to ' + repr(d['main']) + ' and ' if d['attach'] else ''}"
                  f"place panel {d['letter']} at {[round(v) for v in d['frame']]}"
                  f" (lane rect in window {d.get('laneRect')}, fixed-header top {d.get('fallbackTop')})")
        elif "dryRunStemMoves" in p:
            d = p["dryRunStemMoves"]
            print(f"  would {d.get('layout', 'centre')} lane {d['id']} stem controls (height {d['height']}):")
            for m in d["moves"]:
                print(f"    id {m['id']:>4} {m['rect']} -> {m['newRect']}")
        elif "streamBuffer" in p:
            n = p["streamBuffer"]
            print(f"  audio buffer {'in use' if p.get('existing') else 'created'}:"
                  f" 2^{n.bit_length() - 1} samples")
        else:
            print(" ", p)

    script = session.create_script(source)
    script.on("message", on_message)
    script.load()
    signal.signal(signal.SIGINT, lambda *_: print("Still attached; quit Traktor to stop."))
    done.wait()


if __name__ == "__main__":
    main()
