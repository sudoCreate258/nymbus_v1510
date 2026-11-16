# dtom: the browser camera twin

dtom watches you through one or two webcams (plus an optional phone camera), builds a 3D twin from your own body
proportions, and estimates posture, muscle load, fatigue and lower-body time-in-position. It runs entirely in the
browser on this computer. No video or images are saved or sent.

## Run
Double-click `start.bat` (Windows). It opens http://localhost:8765. The phone page is at https://<this PC>:8443/phone
(same Wi-Fi, 6-digit pairing code). A self-signed certificate is created in `./certs/` on first run; it is gitignored.

## Send minutes to Nymbus
Tick "send a 1-minute summary to Nymbus" and paste the ingest token once (from `DTOM_INGEST_TOKEN` in your `.env`).
dtom POSTs `nymbus.twin_minute.v1` documents to http://127.0.0.1:8000/api/twin/minute. Validation lives in
`twin_metrics/dtom.py`. Extra fields dtom adds (activity, stretch_s, drive, relief, lower_body) are accepted and stored.

## Privacy
- The ingest token is kept in this browser only (localStorage `nymbus.token`), never in the page or the repo.
- Saved scans and settings stay in this browser (`nymbus.twin.v1`).
- Exports (`twin-capture-*.json`) are personal data: keep them in `data/inbox/` (gitignored), never commit them.

Estimates only, not a clinical measurement.
