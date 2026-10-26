"""End-to-end tests for the Event RSVP API (stdlib only). Run:  python3 -m unittest discover -s tests -v"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
import server  # noqa: E402

OK = {"title": "Meetup", "location": "Hall", "date_time": "2030-01-01T10:00", "capacity": 2}


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, method, path, body=None, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json", **(headers or {})}
        try:
            conn.request(method, path, body=data, headers=h)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the server may answer 413 and close before we finish sending a huge body
        r = conn.getresponse()
        text = r.read()
        conn.close()
        return r.status, (json.loads(text) if text else None)

    def event(self, **over):
        s, ev = self.call("POST", "/api/events", {**OK, **over})
        self.assertEqual(s, 201, ev)
        return ev

    # --- the original requirements -------------------------------------------------
    def test_crud(self):
        ev = self.event()
        self.assertEqual(self.call("GET", f"/api/events/{ev['id']}")[1]["title"], "Meetup")
        s, upd = self.call("PUT", f"/api/events/{ev['id']}", {**OK, "title": "Renamed"})
        self.assertEqual((s, upd["title"]), (200, "Renamed"))
        self.assertEqual(self.call("DELETE", f"/api/events/{ev['id']}")[0], 204)
        self.assertEqual(self.call("GET", f"/api/events/{ev['id']}")[0], 404)

    def test_capacity_is_enforced_and_yes_count_is_live(self):
        ev = self.event(capacity=1)
        rs = f"/api/events/{ev['id']}/rsvps"
        self.assertEqual(self.call("POST", rs, {"name": "A", "email": "a@x.com", "status": "yes"})[0], 201)
        s, err = self.call("POST", rs, {"name": "B", "email": "b@x.com", "status": "yes"})
        self.assertEqual(s, 409)
        self.assertIn("Event full", err["error"])
        self.assertEqual(self.call("POST", rs, {"name": "B", "email": "b@x.com", "status": "no"})[0], 201)
        got = self.call("GET", f"/api/events/{ev['id']}")[1]
        self.assertEqual((got["yes_count"], got["capacity"], got["full"]), (1, 1, True))

    # --- issues found in the generated code (each failed before the fix) ------------
    def test_capacity_must_be_a_real_whole_number(self):
        for bad in [2.9, True, False, "2.5", "abc", 0, -3, 10**30, None, [1]]:
            s, _ = self.call("POST", "/api/events", {**OK, "capacity": bad})
            self.assertEqual(s, 400, f"capacity {bad!r} should be rejected (was 201/500)")
        self.assertEqual(self.call("POST", "/api/events", {**OK, "capacity": "25"})[0], 201)  # form posts

    def test_date_time_must_be_a_real_date(self):
        for bad in ["tomorrow", "9999-99-99", "31/12/2030", "2030-02-30T10:00", "2030-01-01", "2030-01-01T25:00"]:
            s, err = self.call("POST", "/api/events", {**OK, "date_time": bad})
            self.assertEqual(s, 400, bad)
            self.assertIn("date_time", err["fields"])
        s, ev = self.call("POST", "/api/events", {**OK, "date_time": "2030-01-01 10:30:15"})
        self.assertEqual((s, ev["date_time"]), (201, "2030-01-01T10:30"))

    def test_attendee_emails_are_not_exposed(self):
        ev = self.event()
        self.call("POST", f"/api/events/{ev['id']}/rsvps", {"name": "Zed", "email": "zed@private.com", "status": "yes"})
        body = json.dumps(self.call("GET", f"/api/events/{ev['id']}")[1])
        self.assertIn("Zed", body)
        self.assertNotIn("zed@private.com", body)
        self.assertNotIn("private.com", json.dumps(self.call("GET", "/api/events")[1]))

    def test_field_lengths_and_body_size_are_limited(self):
        self.assertEqual(self.call("POST", "/api/events", {**OK, "title": "x" * 121})[0], 400)
        self.assertEqual(self.call("POST", "/api/events", {**OK, "description": "x" * 2001})[0], 400)
        self.assertEqual(self.call("POST", "/api/events", {**OK, "title": "x" * 2_000_000})[0], 413)
        ev = self.event()
        s, _ = self.call("POST", f"/api/events/{ev['id']}/rsvps", {"name": "n" * 101, "email": "a@x.com", "status": "no"})
        self.assertEqual(s, 400)
        self.assertEqual(self.call("POST", "/api/events", raw=b"{}", headers={"Content-Length": "abc"})[0], 400)

    def test_email_validation_is_strict(self):
        ev = self.event(capacity=50)
        rs = f"/api/events/{ev['id']}/rsvps"
        for bad in ["a@b..c", "a@b.c.", "a@-b.c", "a@b.c d", "a..b@x.com", ".a@x.com", "a@x", "a@x.c", "a@@x.com", "@x.com"]:
            s, err = self.call("POST", rs, {"name": "n", "email": bad, "status": "no"})
            self.assertEqual(s, 400, bad)
        for good in ["a@x.com", "first.last+tag@sub.example.org"]:
            self.assertEqual(self.call("POST", rs, {"name": "n", "email": good, "status": "no"})[0], 201, good)

    def test_required_fields_and_status(self):
        s, err = self.call("POST", "/api/events", {})
        self.assertEqual(s, 400)
        self.assertEqual(set(err["fields"]), {"title", "location", "date_time", "capacity"})
        ev = self.event()
        s, err = self.call("POST", f"/api/events/{ev['id']}/rsvps", {"name": "", "email": "", "status": "maybe"})
        self.assertEqual((s, set(err["fields"])), (400, {"name", "email", "status"}))


if __name__ == "__main__":
    unittest.main()
