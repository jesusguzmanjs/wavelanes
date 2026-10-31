"""Attach wave_height.js to the patched Traktor copy and keep it running.

Waits for "Traktor Pro 4.exe" from the copy folder to start, attaches, and
re-attaches if Traktor is restarted. The script itself stretches the lane
waveforms and keeps the lane panel windows (qml/LanePanel.qml) placed over
them. Stop with Ctrl+C.

    python -I wave_height.py ["%LOCALAPPDATA%\\WaveLanes\\Traktor Pro 4 WaveLanes"]
                             [--launch] [--wave-buffer N]

--launch starts Traktor if it is not running, suspended until the script is
loaded, and exits when Traktor closes. It also lets Traktor's QML read and
write files (QML_XHR_ALLOW_FILE_READ/WRITE), which the settings window
(qml/PanelSettings.qml) needs to keep settings.json.

--wave-buffer N sets the lane waveform ring buffer to 2^N samples (Traktor
uses 21, about 47 s at 44.1 kHz; each step doubles both the sharp window and
its memory, 16 MB per buffer at 21). The buffers are created when Traktor
starts, so this needs --launch.
"""
import ctypes
import functools
import os
import sys
import threading
import time
from pathlib import Path

import frida

print = functools.partial(print, flush=True)

DEFAULT_ROOT = os.path.expandvars(r"%LOCALAPPDATA%\WaveLanes\Traktor Pro 4 WaveLanes")
SCRIPT = Path(__file__).with_name("wave_height.js").read_text(encoding="utf-8")
QML_ENV = {"QML_XHR_ALLOW_FILE_READ": "1", "QML_XHR_ALLOW_FILE_WRITE": "1"}
NO_MAPPING = ("The WaveLanes panels have not appeared. If this is the first time, add the "
              "mapping that carries them, once: Preferences > Controller Manager > Add... > Traktor > "
              "Kontrol Z1 MK2.")

def find_pid(root):
    target = (Path(root) / "Traktor Pro 4.exe").resolve()
    for p in frida.get_local_device().enumerate_processes(scope="full"):
        path = p.parameters.get("path")
        if p.name == "Traktor Pro 4.exe" and path and Path(path).resolve() == target:
            return p.pid
    return None


def take_option(args, name, has_value):
    if name not in args:
        return None
    i = args.index(name)
    value = args[i + 1] if has_value else True
    del args[i:i + (2 if has_value else 1)]
    return value


def main():
    args = sys.argv[1:]
    launch = take_option(args, "--launch", False)
    log2 = take_option(args, "--wave-buffer", True)
    script_source = SCRIPT
    if log2 is not None:
        log2 = int(log2)
        if not 21 <= log2 <= 24:
            sys.exit("--wave-buffer must be between 21 (Traktor's own) and 24")
        if not launch:
            print("Note: --wave-buffer only takes effect on a Traktor started with --launch")
        script_source = SCRIPT.replace("const WAVE_BUFFER_LOG2 = 0;", f"const WAVE_BUFFER_LOG2 = {log2};")
    root = args[0] if args else DEFAULT_ROOT
    exe = Path(root) / "Traktor Pro 4.exe"
    print("Waiting for", exe)
    while True:
        pid = find_pid(root)
        spawned = False
        if pid is None and launch:
            # Started suspended, so the script runs before Traktor builds anything.
            pid = frida.spawn(str(exe), env=QML_ENV)
            spawned = True
        elif pid is None:
            time.sleep(2)
            continue
        else:
            # Give Traktor time to build its main window before scanning.
            time.sleep(8)
        detached = []

        def on_message(message, _):
            payload = message.get("payload", message)
            print(payload)
            if isinstance(payload, dict) and "noMapping" in payload:
                # Not waited for: the messages keep coming while it is open.
                threading.Thread(target=ctypes.windll.user32.MessageBoxW, daemon=True,
                                 args=(None, NO_MAPPING, "WaveLanes", 0x40 | 0x10000)).start()

        try:
            session = frida.attach(pid)
            session.on("detached", lambda reason, crash: detached.append(reason))
            script = session.create_script(script_source)
            script.on("message", on_message)
            script.load()
        except (frida.ProcessNotFoundError, frida.NotSupportedError, frida.TransportError) as e:
            # Traktor exited or was still starting up; wait for the next one.
            print("Attach failed:", e)
            time.sleep(2)
            continue
        if spawned:
            frida.resume(pid)
            print("Launched", pid)
        else:
            print("Attached to", pid)
        while not detached:
            time.sleep(0.5)
        print("Traktor closed:", detached[0])
        if launch:
            # Launch mode starts Traktor once; reopening it is the user's call.
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
