#!/usr/bin/env bash
set -e

# HA Supervisor writes add-on options to /data/options.json
SIDECAR_TOKEN="$(python3 -c "
import json, sys
try:
    print(json.load(open('/data/options.json')).get('sidecar_token', ''))
except (FileNotFoundError, json.JSONDecodeError):
    print('WARNING: /data/options.json not found — starting without token auth', file=sys.stderr)
    print('')
")"
export SIDECAR_TOKEN

# Screenshots go to the mapped addon_config directory
export SCREENSHOT_DIR="/addon_configs/alectra_scraper/screenshots"

echo "Starting Alectra Utilities Scraper on port 8080"
echo "Token configured: $([ -n "$SIDECAR_TOKEN" ] && echo 'yes' || echo 'no')"
echo "Screenshot dir: $SCREENSHOT_DIR"

exec uvicorn app:app --host 0.0.0.0 --port 8080
