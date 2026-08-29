# Darkroom

Local desktop app for an Instagram session: sign in, run paced follower/following scans, and read unfollower reports. Everything stays on your machine. The API binds to `127.0.0.1` only.

Python FastAPI + pywebview (Qt) wrap a Vite/React UI.

## What it does

- **Login** — Opens Chromium so you sign in on Instagram. Darkroom keeps the `sessionid` locally and never asks for your password.
- **Scan** — Crawls your following list, then your followers, with delays between requests. Interrupted scans resume from the last cursor.
- **Report** — After a scan, lists:
  - **Unfollowers** — people you follow who do not follow you back
  - **Vanished** — accounts that were on your following list last scan and are gone now (unfollowed, blocked, or deactivated)
  - **New following** — accounts you started following since the last scan
- **History** — Previous scans for the signed-in account
- **Accounts** — Switch between saved sessions or forget one

## Requirements

- Python 3.11+
- Node.js (for the UI)
- [just](https://github.com/casey/just)
- A desktop environment (Qt window + a Chromium window for login)

On Fedora, Qt and Chromium system libraries are typically already present once Playwright installs its browser.

## Install

```bash
just install
```

Creates `.venv`, installs the Python package, downloads Playwright Chromium, and installs UI packages.

## Run

```bash
just run
```

Builds the production UI and opens the desktop window. FastAPI serves `ui/dist` on `http://127.0.0.1:8765`.

For development (Vite HMR in the native window, API still on `:8765`):

```bash
just dev
```

Vite listens on `http://127.0.0.1:5173` and proxies `/api` to the backend.

## How a scan works

A scan is two paced crawls of the signed-in account (following, then followers), stored in SQLite.

- instagrapi waits a random 3–7 seconds after each private request
- Instagram pages return ~50–100 users; Darkroom requests 100 per page
- Rate limits trigger a 30-minute wait (up to three times), then the scan stops with progress saved

Do not change those delays to hammer Instagram. Large accounts take a long time; that is expected.

## Data

Runtime files live in `~/darkroom/` (never commit this directory):

| Path | What |
| --- | --- |
| `sessions/{pk}.json` | Saved instagrapi session per account |
| `sessions/current` | Which account is active |
| `darkroom.db` | Accounts, scans, members, events |
| `avatars/` | Cached profile pictures |
| `webview/` | Qt WebEngine storage |

Session cookies and passwords are not logged. Sign-out deactivates the current session; forgetting an account deletes its session file.

## Layout

```
src/darkroom/     Python package
  __main__.py     uvicorn on :8765 + native window
  api.py          FastAPI
  login.py        Playwright → sessionid → instagrapi
  scan.py         Background scan threads
  db.py           SQLite
ui/               React 19, Vite 8, Tailwind 4, shadcn
```

## Notes

This uses Instagram’s unofficial private API via [instagrapi](https://github.com/subzeroid/instagrapi). Instagram can rate-limit, challenge, or expire a session. If that happens, wait, sign in from the official app, then try again from Darkroom.
