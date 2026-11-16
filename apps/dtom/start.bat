@echo off
REM Nymbus twin capture: PC page http://localhost:8765 + phone pairing https://<this PC>:8443/phone
REM Keep this window open while you use it. Close it to stop.
cd /d "%~dp0"

where py >nul 2>nul && (start "" http://localhost:8765 & py server.py & goto :end)
python -c "import sys" >nul 2>nul && (start "" http://localhost:8765 & python server.py & goto :end)

echo Python not found - using the official python Docker image (Docker Desktop must be running)...
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -ne $null} | Select-Object -First 1).IPv4Address.IPAddress"`) do set LANIP=%%i
echo LAN address: %LANIP%
start "" http://localhost:8765
docker run --rm -it -p 127.0.0.1:8765:8765 -p 8443:8443 -e NYMBUS_IN_DOCKER=1 -e NYMBUS_LAN_IP=%LANIP% -v "%CD%:/srv" -w /srv python:3.12-alpine sh -c "apk add --no-cache openssl >/dev/null && python server.py"

:end
pause
