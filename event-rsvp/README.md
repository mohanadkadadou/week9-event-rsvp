# Event RSVP

A small Event RSVP web app: create/edit/delete events, RSVP yes/no, capacity enforcement with a live "X / N going" count.

**Stack:** Python 3 standard library only (`http.server` + `sqlite3`), plain HTML/JS frontend. No dependencies to install.

## Prerequisites
- Python 3.8+ (no pip packages needed)

## Install
Nothing to install. The SQLite database (`events.db`) is created automatically on first run and persists between restarts.

## Run
```
cd event-rsvp
python3 server.py
```
Open http://127.0.0.1:8000

## Environment variables (all optional)
- `PORT` - port to listen on (default `8000`)
- `HOST` - bind address (default `127.0.0.1`)
- `DB_PATH` - SQLite file path (default `./events.db`)

## API
- `GET/POST /api/events`, `GET/PUT/DELETE /api/events/{id}`
- `POST /api/events/{id}/rsvps` with `{name, email, status: "yes"|"no"}`

## Behavior notes
- One RSVP per email per event; re-submitting updates the previous one (so a "yes" can be changed to "no" when full).
- "yes" RSVPs are rejected with "Event full" (HTTP 409) once capacity is reached.
- Lowering capacity below the current yes count is allowed; no one is removed, but the event shows as full.
- No authentication: anyone can edit or delete events.
