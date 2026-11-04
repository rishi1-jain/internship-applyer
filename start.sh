#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python3 ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/ and try again.' >&2
    exit 1
  fi
  python3 -m venv .venv
fi
if ! .venv/bin/python3 -c 'import reportlab' >/dev/null 2>&1; then
  .venv/bin/python3 -m pip install -r requirements.txt
fi
exec .venv/bin/python3 server.py "$@"
