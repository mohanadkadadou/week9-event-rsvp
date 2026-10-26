# Week 9 Writeup: The Software Factory (Event RSVP)

**Mohanad Kadadou (2309115218).** App: [`event-rsvp/`](event-rsvp). Tests: `python3 -m unittest discover -s event-rsvp/tests -v` (8 tests).

## Deviation first: bolt.new was not used
bolt.new needs an account and credits that I (Claude Code) cannot create or claim for you, so I did **not** use it. To keep the exercise honest I used a different generator: a fresh Claude (Sonnet 5.5) subagent told to act as "an AI app-generation platform" and given the exact text of [`PROMPT.md`](PROMPT.md) with no other guidance. Its output is committed **unmodified** as the first commit (`git log`), so the evaluate-and-fix step below is real, not staged. If you want the bolt.new version for grading, paste `PROMPT.md` into bolt.new and run the same checks (the issue list below is a good checklist); I can redo this write-up around it.

## Prompt and iterations
- **Prompt:** the `PROMPT.md` text verbatim, plus "build it in one pass, include a README, run it once".
- **Iterations: 1.** No re-prompting. The generator chose Python stdlib (`http.server` + `sqlite3`) and a single-page vanilla JS frontend, so there is nothing to install.
- What it got right: full CRUD, RSVP yes/no, capacity enforced with "Event full" (HTTP 409), a live "N / capacity" badge, persistent SQLite, output escaping in the UI (no XSS), foreign-key cascade on delete, a lock around writes, a clear README. It reported honestly that it had no tests, no auth and no browser check.

## Issues I found by reviewing and probing the running server (5, fixed by hand with Claude Code, not by re-prompting)
| # | Issue (evidence from the generated code) | Impact | Fix |
|---|---|---|---|
| 1 | `capacity` coerced with `int()`: `2.9` and `true` were accepted (as 2 and 1), and `10**30` crashed with **HTTP 500** | wrong data, server error on user input | strict whole number 1..100000; reject bool/float/huge |
| 2 | `date_time` was never validated: `"tomorrow"`, `"9999-99-99"`, `"31/12/2030"` all stored with 201, and the event list sorts by that string, so ordering is wrong | corrupt data, broken "upcoming events" | require a real date-time, normalise to `YYYY-MM-DDTHH:MM` |
| 3 | `GET /api/events/{id}` returned **every attendee's email** to anyone (the UI only shows names) | PII leak (privacy) | emails stay server-side; API returns name + status only |
| 4 | No length or body-size limits: a 2 MB title was accepted | storage abuse / DoS | field limits (120/120/2000/100/254) and a 64 KB body cap (413); invalid `Content-Length` -> 400 |
| 5 | Email regex `^[^@\s]+@[^@\s]+\.[^@\s]+$` accepted `a@b..c` and `a@b.c.` | junk addresses count against capacity | stricter local-part/label/TLD rules |

Verification: I wrote 8 end-to-end tests first. Run against the **unmodified generated server**, **5 of 8 fail** (issues 1-5); after the fixes all 8 pass, three runs in a row. I also loaded the app in a browser to confirm the UI still works end to end (event with 2/2 going shows "Event full", attendees listed by name only): [`docs/ui-event-full.jpg`](docs/ui-event-full.jpg). Left alone on purpose: no authentication (anyone can edit or delete events; the generator documented it), no pagination, past dates allowed.

## What I learned
Generating the app took about a minute and got the happy path right, but every defect I found sat in the unglamorous edges (input coercion, unvalidated fields, a privacy leak, missing limits), exactly where a prompt that lists features says nothing, so the engineer's job really is to evaluate and integrate: write the tests the platform did not, and probe like an attacker. Building by hand would have been slower but would have forced those decisions up front; generation moves them to review time, which only works if someone actually reviews. If this app had to improve itself with minimal human input, the first thing to break is the **definition of "correct"**: with no tests and only a feature prompt, a self-editing loop would happily "improve" the app while silently reintroducing leaks or 500s. The guardrail I'd add is a human-owned, non-editable test and security gate (these 8 tests plus a PII/limits check) that every self-made change must pass before it ships.
