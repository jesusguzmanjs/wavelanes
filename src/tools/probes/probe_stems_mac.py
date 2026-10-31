"""Read-only trace of when Traktor expands or collapses the lane stem headers.

Logs every StemControls::toggle() call (with the flag before and after and the
calling function), every DeckWaveDisplayForm::onControlEvent for the stem
arrow, and the flag after each track load on the UI thread. Changes nothing;
runs for DURATION seconds, then unhooks and detaches.

    .venv/bin/python -I tools/probes/probe_stems_mac.py
"""
import json
import sys
import time

import frida

PROCESS = "Traktor Pro 4"
DURATION = 120

SCRIPT = r"""
const main = Process.mainModule;
const sym = n => { const a = main.findSymbolByName(n); if (!a) throw new Error(n); return a; };
const FORM_ID = 0x24, FORM_STEMS = 0x618, STEMS_EXPANDED = 0x1d8;
const stemsOwner = new Map();

function laneId(form) { return form.add(FORM_ID).readU32(); }
function caller(ctx) {
  const s = DebugSymbol.fromAddress(ctx.lr);
  return s.name || ctx.lr.toString();
}

Interceptor.attach(sym('_ZN19DeckWaveDisplayForm12StemControls6toggleEv'), {
  onEnter(args) { this.s = args[0]; this.before = args[0].add(STEMS_EXPANDED).readU8(); this.from = caller(this.context); },
  onLeave() {
    send({toggle: {lane: stemsOwner.get(this.s.toString()) || null, before: this.before,
                   after: this.s.add(STEMS_EXPANDED).readU8(),
                   available: [this.s.add(0x18).readU8(), this.s.add(0x19).readU8()], from: this.from}});
  },
});

Interceptor.attach(sym('_ZN19DeckWaveDisplayForm14onControlEventEjjPN2NI3NGL16ControlEventDataE'), {
  onEnter(args) {
    const form = args[0];
    const stems = form.add(FORM_STEMS).readPointer();
    if (!stems.isNull()) stemsOwner.set(stems.toString(), laneId(form));
    this.row = {lane: laneId(form), control: args[1].toUInt32(), event: args[2].toUInt32(), from: caller(this.context)};
  },
  onLeave(ret) {
    if (this.row.control === 64) send({controlEvent: this.row});
  },
});

Interceptor.attach(sym('_ZN19DeckWaveDisplayForm36onTrackPlayerStreamChangedMainThreadEv'), {
  onEnter(args) { this.form = args[0]; },
  onLeave() {
    const stems = this.form.add(FORM_STEMS).readPointer();
    if (stems.isNull()) return;
    stemsOwner.set(stems.toString(), laneId(this.form));
    send({trackLoaded: {lane: laneId(this.form), expanded: stems.add(STEMS_EXPANDED).readU8(),
                        available: [stems.add(0x18).readU8(), stems.add(0x19).readU8()]}});
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
