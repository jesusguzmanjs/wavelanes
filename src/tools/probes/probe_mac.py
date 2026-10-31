"""Read-only check that Frida can attach to the running Traktor copy on macOS.

Attaches, resolves the symbols the waveform script will hook, prints them and
detaches. It installs no hooks and neither scans nor writes memory.

    .venv/bin/python -I tools/probes/probe_mac.py
"""
import json
import sys

import frida

PROCESS = "Traktor Pro 4"

# Local (non-exported) symbols of the arm64 slice, as nm prints them minus the
# leading underscore. Static offsets from nm are listed for comparison.
SYMBOLS = {
    "_ZN19DeckWaveDisplayForm14resizeWaveformEv": 0x92B440,
    "_ZN19DeckWaveDisplayForm16onLayoutControlsERKN2NI2GP5PointE": 0x92B580,
    "_ZN19DeckWaveDisplayForm12StemControls6toggleEv": 0x9295FC,
    "_ZN12StreamBuffer4initEjjjf": 0x1EB7A8,
    "_ZN12StreamBufferC2Ejb": 0x1F24D8,
}

SCRIPT = r"""
const main = Process.mainModule;
const found = {};
for (const name of %s) {
  const a = main.findSymbolByName(name);
  found[name] = a ? "0x" + a.sub(main.base).toString(16) : null;
}
send({ arch: Process.arch, pid: Process.id, module: main.name, base: main.base.toString(), found: found });
""" % json.dumps(list(SYMBOLS))


def main():
    try:
        session = frida.attach(PROCESS)
    except frida.ProcessNotFoundError:
        sys.exit(f"{PROCESS} is not running")
    result = {}
    script = session.create_script(SCRIPT)
    script.on("message", lambda m, _: result.update(m.get("payload") or {"error": m}))
    script.load()
    script.unload()
    session.detach()
    if "error" in result:
        sys.exit(result["error"])
    print(f"{result['module']} pid {result['pid']} ({result['arch']}), base {result['base']}")
    for name, static in SYMBOLS.items():
        got = result["found"][name]
        # nm offsets include the 0x100000000 image base, already stripped above.
        status = "ok" if got and int(got, 16) == static else f"nm says {static:#x}"
        print(f"  {got or 'MISSING':>10}  {status:<16} {name}")


if __name__ == "__main__":
    main()
