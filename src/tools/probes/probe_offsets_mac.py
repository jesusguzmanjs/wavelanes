"""Read-only check of the ARM64 field offsets used by the waveform script.

Hooks DeckWaveDisplayForm::resizeWaveform without changing anything, logs the
candidate fields of every lane form that passes through it for DURATION
seconds, then unhooks and detaches. Resize Traktor's window meanwhile, so the
lanes are laid out again.

    .venv/bin/python -I tools/probes/probe_offsets_mac.py
"""
import json
import sys
import time

import frida

PROCESS = "Traktor Pro 4"
DURATION = 90

SCRIPT = r"""
const main = Process.mainModule;
const resize = main.findSymbolByName('_ZN19DeckWaveDisplayForm14resizeWaveformEv');
const seen = new Map();
Interceptor.attach(resize, {
  onEnter(args) { this.form = args[0]; },
  onLeave() {
    const f = this.form;
    const wave = f.add(0x338).readPointer();
    const row = {
      form: f.toString(),
      id: f.add(0x24).readU32(),
      visibleSize: [f.add(0x40).readS32(), f.add(0x44).readS32()],
      deckIndex: f.add(0x608).readU32(),
      wave: wave.toString(),
      waveRect: wave.isNull() ? null : [0x38, 0x3c, 0x40, 0x44].map(o => wave.add(o).readS32()),
    };
    const key = JSON.stringify(row);
    if (seen.get(f.toString()) !== key) {
      seen.set(f.toString(), key);
      send(row);
    }
  },
});
send({ready: true});
"""


def main():
    try:
        session = frida.attach(PROCESS)
    except frida.ProcessNotFoundError:
        sys.exit(f"{PROCESS} is not running")
    script = session.create_script(SCRIPT)
    script.on("message", lambda m, _: print(json.dumps(m.get("payload", m)), flush=True))
    script.load()
    try:
        time.sleep(DURATION)
    finally:
        script.unload()
        session.detach()
    print("detached")


if __name__ == "__main__":
    main()
