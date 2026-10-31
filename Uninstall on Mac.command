#!/bin/sh
# Double-click to remove WaveLanes: the Traktor copy, its backups, the
# launcher, the signing certificate and the settings. Asks first; the original Traktor is
# not touched.
cd "$(dirname "$0")/src" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "WaveLanes was not installed from this folder (no .venv)."
    exit 1
fi
.venv/bin/python -I mac/install_mac.py --uninstall "$@"
echo
echo "You can close this window."
