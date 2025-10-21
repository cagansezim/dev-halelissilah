#!/usr/bin/env sh
set -e

ROOT="${1:-.}"

# always use the Python patcher (portable; robust)
python3 "$(dirname "$0")/patch_pydantic_fields.py" "$ROOT" || {
  echo "pydantic field patcher failed (non-fatal)"; exit 0;
}
