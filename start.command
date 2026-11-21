#!/bin/bash
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
printf '\nOpen http://127.0.0.1:5050 in your browser. Press Control-C to stop.\n\n'
.venv/bin/python app.py
