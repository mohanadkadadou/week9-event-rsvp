# Starter prompt — Event RSVP app

Paste this into [bolt.new](https://bolt.new/) as your starting prompt, then iterate.
It is intentionally specific about entities and flows so the generator has enough to
work with. Adapt wording to taste.

---

Build a small **Event RSVP** web app.

**Entities**
- `Event`: title, description, date/time, location, capacity (integer).
- `RSVP`: attendee name, email, status (`yes` / `no`), linked to an event.

**Features**
- Create, view, edit, and delete events (CRUD).
- On an event page, a visitor can RSVP `yes` or `no` with their name and email.
- Enforce capacity: block new `yes` RSVPs once the event is full; show "Event full".
- Show a live count of `yes` RSVPs vs. capacity on each event.
- Basic validation (required fields, valid email) and friendly error messages.

**Tech**
- Any modern full-stack default the generator prefers.
- Persistent storage (a database or file store).
- A clean, simple UI that surfaces: list of events, event detail + RSVP form, and a
  "create event" form.

**Deliverable**
- A running app with clear instructions to run it locally.
