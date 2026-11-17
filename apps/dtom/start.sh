#!/usr/bin/env bash
# dtom: PC page http://localhost:8765 + phone pairing https://<this PC>:8443/phone (any number of phones: C, D, E ...)
# Keep this terminal open while you use it. Ctrl+C to stop.
set -e
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  (sleep 2; xdg-open http://localhost:8765 >/dev/null 2>&1 || open http://localhost:8765 >/dev/null 2>&1 || true) &
  exec python3 server.py
fi
echo "python3 not found - using the official python Docker image (Docker must be running)..."
LANIP=$(hostname -I 2>/dev/null | awk '{print $1}')
(sleep 4; xdg-open http://localhost:8765 >/dev/null 2>&1 || true) &
exec docker run --rm -it -p 127.0.0.1:8765:8765 -p 8443:8443 -e NYMBUS_IN_DOCKER=1 -e NYMBUS_LAN_IP="$LANIP" \
  -v "$PWD:/srv" -w /srv python:3.12-alpine sh -c "apk add --no-cache openssl >/dev/null && python server.py"
