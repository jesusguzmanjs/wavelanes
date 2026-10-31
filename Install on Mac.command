#!/bin/sh
# Double-click to install WaveLanes (or open it again to repair or update
# the install). Makes the Python environment in src, then runs
# src/mac/install_mac.py.
cd "$(dirname "$0")/src" || exit 1

if ! xcode-select -p >/dev/null 2>&1; then
    echo "macOS's command line tools are needed (they bring Python)."
    echo "Install them in the window that opens, then open this file again."
    xcode-select --install
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Making the Python environment..."
    /usr/bin/python3 -m venv .venv || exit 1
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt || exit 1

.venv/bin/python -I mac/install_mac.py "$@"
echo
echo "You can close this window."
