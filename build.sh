#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv-posix/bin/python ]]; then
  python3 -m venv .venv-posix
fi

.venv-posix/bin/python -m pip install -e '.[build]'
.venv-posix/bin/python -m PyInstaller --noconfirm --clean kinebeat.spec
