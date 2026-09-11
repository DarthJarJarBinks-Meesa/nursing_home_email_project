#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

KEY="$(python3 -c "from pathlib import Path; s=Path('.env').read_text(encoding='utf-8').strip(); print(s.split('=',1)[1].strip() if '=' in s else '')")"
if [[ -z "${KEY}" ]]; then
  echo "ERROR: No BRAVE_API_KEY in .env" >&2
  echo "Create a .env file with: export BRAVE_API_KEY=your_key_here" >&2
  exit 1
fi
export BRAVE_API_KEY="${KEY}"

# Prefer project venv if present, otherwise fall back to python3 on PATH.
if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "ERROR: Python 3 not found. Install Python 3 and/or create .venv (see README.md)." >&2
  exit 1
fi

if ! "$PYTHON" -c "import pandas" >/dev/null 2>&1; then
  echo "ERROR: pandas is not installed for: $PYTHON" >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PYTHON" -u "find_nursing_home_emails.py" "$@"
