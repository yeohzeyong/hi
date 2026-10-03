#!/usr/bin/env bash
# macOS/Linux: run the full pipeline using your Chrome. Add to cron:
#   7 7 * * * /path/to/repo/run_local.sh >> /tmp/auction.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-browser.txt; }
.venv/bin/python -m auction_tracker run --backend auto
