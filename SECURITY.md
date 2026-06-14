# Security Policy

## What this tool does (transparency)

ASA Log Agent reads a **screen region** with OCR and sends parsed ARK tribe-log
lines to a bot endpoint. It is deliberately minimal and auditable:

- **Screen-only.** It never reads, writes, or attaches to the game process or
  memory. It only captures a screenshot region (see `ocr.py`, `mss`).
- **Sends only real tribe-log lines.** A line is sent **only** if it starts with
  a `Day N, HH:MM:SS:` header (see the hard filter in `logparse.py`). UI text,
  chat, menus, and anything else on screen are dropped — on the agent side and
  again server-side.
- **No telemetry, no background calls.** The only network call is the
  authenticated `POST` to the configured `api_url` (see `asa_log_agent.py`).
- **Local state** (config, queue, screenshot) lives in
  `%LOCALAPPDATA%\ASALogAgent`. Nothing is uploaded except parsed log events.

## Token handling

- Each user generates a personal token in Discord with `/log key`. It is stored
  locally in `agent.ini` and sent as a `Bearer` token. Revoke any time with
  `/log revoke`, rotate with `/log key`.
- **Never commit your filled `agent.ini`** — the tracked copy ships with an
  empty token on purpose.

## Transport note (read before using a public endpoint)

The default `api_url` uses `http://`. If you point the agent at an endpoint over
plain HTTP, the bearer token travels in cleartext and could be intercepted on an
untrusted network. **Use an `https://` endpoint** (e.g. behind a TLS reverse
proxy / Cloudflare) for anything beyond local testing.

## Reporting a vulnerability

Please report privately via GitHub **Security advisories**
("Report a vulnerability" on the Security tab) rather than a public issue.
We aim to respond within a few days.
