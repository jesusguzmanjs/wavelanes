"""The settings in settings.json that need Traktor closed to apply.

The settings window inside Traktor (qml/PanelSettings.qml) keeps all its
settings in settings.json, in the user's own data folder (UI), so
that a new download of this folder keeps them. Most apply at once.
The layout ones (hideDecks, hideBrowser, lanes, laneHeight, waveBuffer) are
patched into
Traktor's copy, which can only happen with Traktor closed: the launcher reads
them here before opening Traktor, applies what changed (mac/traktor_config.py)
and records what it applied in "applied":

    {"hideDecks": true, "lanes": 3, ..., "applied": {"hideDecks": true, ...}}

The window shows a layout setting that differs from "applied" as waiting for
a restart, and can put it back. A file without them gets the defaults. Shared
by mac/ and windows/.
"""
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    DATA = Path(os.environ["LOCALAPPDATA"]) / "WaveLanes"
else:
    DATA = Path.home() / "Library" / "Application Support" / "WaveLanes"
UI = DATA / "settings.json"
# Where it was kept before, under its old name, at the root of this repo.
OLD_UI = Path(__file__).resolve().parent.parent / "traktor-custom.ui.json"
LAYOUT_DEFAULTS = {"hideDecks": True, "hideBrowser": False, "lanes": 3, "laneHeight": 216, "waveBuffer": 22}


class SettingsError(Exception):
    pass


def read(ui=UI):
    """The whole file, or {} if there is none yet."""
    if not ui.exists():
        return {}
    try:
        settings = json.loads(ui.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SettingsError(f"{ui.name} is not valid JSON: {e}")
    if not isinstance(settings, dict):
        raise SettingsError(f"{ui.name} does not hold an object")
    return settings


def prepare(ui=UI):
    """Make the folder the window writes the file to (it cannot make one),
    and bring the file over from where it was kept before."""
    ui.parent.mkdir(parents=True, exist_ok=True)
    if ui == UI and not ui.exists() and OLD_UI.exists():
        OLD_UI.replace(ui)


def layout(ui=UI):
    """The layout settings as the window left them, checked; defaults for the missing ones."""
    prepare(ui)
    settings = read(ui)
    p = {key: settings.get(key, value) for key, value in LAYOUT_DEFAULTS.items()}
    if type(p["hideDecks"]) is not bool:
        raise SettingsError(f"{ui.name}: hideDecks must be true or false, not {p['hideDecks']!r}")
    if type(p["hideBrowser"]) is not bool:
        raise SettingsError(f"{ui.name}: hideBrowser must be true or false, not {p['hideBrowser']!r}")
    if type(p["lanes"]) is not int or p["lanes"] not in (3, 4):
        raise SettingsError(f"{ui.name}: lanes must be 3 or 4, not {p['lanes']!r}")
    if type(p["laneHeight"]) is not int or p["laneHeight"] < 91:
        raise SettingsError(f"{ui.name}: laneHeight must be a whole number of at least 91, not {p['laneHeight']!r}")
    if type(p["waveBuffer"]) is not int or not 21 <= p["waveBuffer"] <= 24:
        raise SettingsError(f"{ui.name}: waveBuffer must be a whole number from 21 to 24, not {p['waveBuffer']!r}")
    return p


def set_applied(values, ui=UI):
    """Record the layout settings now in Traktor's copy (with Traktor closed)."""
    settings = read(ui)
    if settings.get("applied") == values and all(key in settings for key in values):
        return
    settings["applied"] = dict(values)
    # The window reads these on start: write the defaults out the first time.
    for key, value in values.items():
        settings.setdefault(key, value)
    ui.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
