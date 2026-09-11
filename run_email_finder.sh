#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
KEY="$(python3 -c "from pathlib import Path; s=Path('.env').read_text(encoding='utf-8').strip(); print(s.split('=',1)[1].strip() if '=' in s else '')")"
if [[ -z "${KEY}" ]]; then
  echo "ERROR: No BRAVE_API_KEY in .env" >&2
  exit 1
fi
export BRAVE_API_KEY="${KEY}"
exec "/opt/miniconda3/bin/python" -u "find_nursing_home_emails.py" "$@"
