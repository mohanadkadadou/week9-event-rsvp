"""Event RSVP app: Python 3 standard library only (http.server + sqlite3)."""
import json, os, re, sqlite3, threading
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "events.db"))
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "127.0.0.1")
LOCK = threading.Lock()
# --- limits and strict validation (added after reviewing the generated code; see writeup.md) ---
MAX_BODY = 64 * 1024
LIMITS = {"title": 120, "location": 120, "description": 2000, "name": 100, "email": 254}
MAX_CAPACITY = 100_000
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
EMAIL_RE = re.compile(rf"^[A-Za-z0-9!#$%&'*+/=?^_`{{|}}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{{|}}~-]+)*@(?:{_LABEL}\.)+[A-Za-z]{{2,}}$")


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', date_time TEXT NOT NULL,
          location TEXT NOT NULL, capacity INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS rsvps(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          name TEXT NOT NULL, email TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('yes','no')),
          UNIQUE(event_id, email));
        """)


class ApiError(Exception):
    def __init__(self, code, msg, fields=None):
        self.code, self.msg, self.fields = code, msg, fields or {}


def parse_capacity(v):
    """Whole number 1..MAX_CAPACITY; accepts ints and digit strings (form posts), rejects bools/floats."""
    if isinstance(v, bool) or isinstance(v, float):
        return None
    if isinstance(v, str) and re.fullmatch(r"\d{1,9}", v.strip()):
        v = int(v.strip())
    if isinstance(v, int) and 1 <= v <= MAX_CAPACITY:
        return v
    return None


def parse_date_time(v):
    """Real calendar date-time (YYYY-MM-DDTHH:MM[:SS]); stored normalised to YYYY-MM-DDTHH:MM."""
    v = str(v).strip().replace(" ", "T", 1)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", v):
        return None
    try:
        return datetime.fromisoformat(v).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def clean_event(d):
    errs = {}
    title = str(d.get("title", "")).strip()
    loc = str(d.get("location", "")).strip()
    desc = str(d.get("description", "")).strip()
    if not title: errs["title"] = "Title is required."
    elif len(title) > LIMITS["title"]: errs["title"] = f"Title must be at most {LIMITS['title']} characters."
    if not loc: errs["location"] = "Location is required."
    elif len(loc) > LIMITS["location"]: errs["location"] = f"Location must be at most {LIMITS['location']} characters."
    if len(desc) > LIMITS["description"]: errs["description"] = f"Description must be at most {LIMITS['description']} characters."
    raw_dt = str(d.get("date_time", "")).strip()
    dt = parse_date_time(raw_dt) if raw_dt else None
    if not raw_dt: errs["date_time"] = "Date and time are required."
    elif dt is None: errs["date_time"] = "Enter a valid date and time (YYYY-MM-DDTHH:MM)."
    cap = parse_capacity(d.get("capacity"))
    if cap is None: errs["capacity"] = f"Capacity must be a whole number from 1 to {MAX_CAPACITY}."
    if errs: raise ApiError(400, "Please fix the highlighted fields.", errs)
    return title, desc, dt, loc, cap


def event_json(c, row):
    yes = c.execute("SELECT COUNT(*) FROM rsvps WHERE event_id=? AND status='yes'", (row["id"],)).fetchone()[0]
    return {"id": row["id"], "title": row["title"], "description": row["description"],
            "date_time": row["date_time"], "location": row["location"],
            "capacity": row["capacity"], "yes_count": yes, "full": yes >= row["capacity"]}


def get_event(c, eid):
    row = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    if not row: raise ApiError(404, "Event not found.")
    return row


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, obj=None, ctype="application/json", raw=None):
        body = raw if raw is not None else (b"" if obj is None else json.dumps(obj).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_any(self, method):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path.startswith("/api/"):
                body = {}
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    raise ApiError(400, "Invalid Content-Length.")
                if n < 0: raise ApiError(400, "Invalid Content-Length.")
                if n > MAX_BODY: raise ApiError(413, "Request body too large.")
                if n:
                    try: body = json.loads(self.rfile.read(n))
                    except ValueError: raise ApiError(400, "Invalid JSON.")
                    if not isinstance(body, dict): raise ApiError(400, "Invalid JSON.")
                with LOCK, db() as c:
                    self.send(*self.route(c, method, path.split("/")[2:], body))
            elif method == "GET":
                fp = os.path.join(BASE, "static", "index.html")
                with open(fp, "rb") as f:
                    self.send(200, ctype="text/html; charset=utf-8", raw=f.read())
            else:
                raise ApiError(405, "Method not allowed.")
        except ApiError as e:
            self.send(e.code, {"error": e.msg, "fields": e.fields})
        except Exception:
            self.send(500, {"error": "Something went wrong on the server.", "fields": {}})

    def route(self, c, m, p, body):
        if p == ["events"]:
            if m == "GET":
                rows = c.execute("SELECT * FROM events ORDER BY date_time").fetchall()
                return 200, [event_json(c, r) for r in rows]
            if m == "POST":
                cur = c.execute("INSERT INTO events(title,description,date_time,location,capacity) VALUES(?,?,?,?,?)", clean_event(body))
                return 201, event_json(c, get_event(c, cur.lastrowid))
        elif len(p) >= 2 and p[0] == "events" and p[1].isdigit():
            eid = int(p[1]); row = get_event(c, eid)
            if len(p) == 2:
                if m == "GET":
                    ev = event_json(c, row)
                    ev["rsvps"] = [dict(r) for r in c.execute("SELECT id,name,status FROM rsvps WHERE event_id=? ORDER BY id", (eid,))]  # emails are private
                    return 200, ev
                if m == "PUT":
                    t = clean_event(body)
                    c.execute("UPDATE events SET title=?,description=?,date_time=?,location=?,capacity=? WHERE id=?", t + (eid,))
                    return 200, event_json(c, get_event(c, eid))
                if m == "DELETE":
                    c.execute("DELETE FROM events WHERE id=?", (eid,))
                    return 204, None
            elif p[2:] == ["rsvps"] and m == "POST":
                errs = {}
                name = str(body.get("name", "")).strip()
                email = str(body.get("email", "")).strip().lower()
                status = body.get("status")
                if not name: errs["name"] = "Name is required."
                elif len(name) > LIMITS["name"]: errs["name"] = f"Name must be at most {LIMITS['name']} characters."
                if not email: errs["email"] = "Email is required."
                elif len(email) > LIMITS["email"] or not EMAIL_RE.match(email): errs["email"] = "Please enter a valid email address."
                if status not in ("yes", "no"): errs["status"] = "Choose yes or no."
                if errs: raise ApiError(400, "Please fix the highlighted fields.", errs)
                prev = c.execute("SELECT * FROM rsvps WHERE event_id=? AND email=?", (eid, email)).fetchone()
                if status == "yes" and not (prev and prev["status"] == "yes"):
                    yes = c.execute("SELECT COUNT(*) FROM rsvps WHERE event_id=? AND status='yes'", (eid,)).fetchone()[0]
                    if yes >= row["capacity"]:
                        raise ApiError(409, "Event full. No more 'yes' RSVPs are being accepted.")
                if prev:
                    c.execute("UPDATE rsvps SET name=?, status=? WHERE id=?", (name, status, prev["id"]))
                else:
                    c.execute("INSERT INTO rsvps(event_id,name,email,status) VALUES(?,?,?,?)", (eid, name, email, status))
                return 201, event_json(c, row)
        raise ApiError(404, "Not found.")

    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")
    def do_DELETE(self): self.handle_any("DELETE")


if __name__ == "__main__":
    init_db()
    print(f"Event RSVP running at http://{HOST}:{PORT}  (db: {DB_PATH})")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
