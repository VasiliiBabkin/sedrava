"""Real SQLite + ASGI tests for 0.13 A2 test-only typed API (no public auth)."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sedrava_server_schema import build_server, parse_server
from sedrava_server_runtime import make_app, migrate_database

SOURCE = '''server "Restricted taskboard"
database sqlite env SEDRAVA_A2_TEST_DB
migration 1:
    create table tasks:
        title: text(160)
        done: bool
migration 2:
    add column tasks.note: text(300) default ""
endpoint GET "/api/tasks" -> list tasks
endpoint POST "/api/tasks" -> create tasks
endpoint GET "/api/tasks/{id}" -> read tasks
endpoint PATCH "/api/tasks/{id}" -> update tasks
endpoint DELETE "/api/tasks/{id}" -> delete tasks
'''
TOKEN = "the-local-test-only-token-is-long-enough-1234567890"


class API013Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="sedrava a2 sqlite ")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "db.sqlite"
        self.output = self.root / "generated"
        self.env = patch.dict(os.environ, {
            "SEDRAVA_A2_TEST_DB": str(self.db),
            "SEDRAVA_API_EXPERIMENTAL_ENABLE": "1",
            "SEDRAVA_API_EXPERIMENTAL_TOKEN": TOKEN,
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        build_server(SOURCE, self.output)
        migrate_database(self.output)
        self.app = make_app(self.output)

    def request(self, method, path, obj=None, *, headers=(), query=b"", raw=None,
                host=b"127.0.0.1:8000", client="127.0.0.1", server="127.0.0.1"):
        if raw is None and obj is not None:
            raw = json.dumps(obj).encode("utf-8")
        if raw is None:
            raw = b""
        request_headers = [
            (b"host", host),
            (b"authorization", ("Bearer " + TOKEN).encode()),
        ]
        if obj is not None or raw:
            request_headers.append((b"content-type", b"application/json"))
        request_headers.extend(headers)
        scope = {
            "type": "http", "method": method, "path": path,
            "raw_path": path.encode("ascii", "backslashreplace"),
            "headers": request_headers, "query_string": query,
            "client": (client, 9000), "server": (server, 8000),
        }
        events = []
        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}
        async def send(event):
            events.append(event)
        asyncio.run(self.app(scope, receive, send))
        return (events[0]["status"], json.loads(events[1]["body"]),
                dict(events[0]["headers"]))

    def create(self, title="First", done=False):
        code, data, hdr = self.request("POST", "/api/tasks", {"title": title, "done": done})
        self.assertEqual(code, 201, data)
        return data["item"], hdr[b"etag"]

    def test_route_contract_and_invalid_or_duplicated_source(self):
        actual = parse_server(SOURCE)
        self.assertEqual(len(actual["routes"]), 5)
        self.assertEqual(actual["routes"][0]["action"], "list")
        bad = [
            SOURCE + 'endpoint GET "/api/tasks" -> list tasks\n',
            SOURCE.replace('-> list tasks', '-> delete tasks'),
            SOURCE.replace('-> create tasks', '-> create users'),
            SOURCE.replace('"/api/tasks/{id}"', '"/api/tasks/{slug}"'),
            SOURCE.replace('GET "/api/tasks"', 'PUT "/api/tasks"'),
            SOURCE.replace('"/api/tasks"', '"/api/users"'),
            SOURCE.replace('endpoint GET', 'endpoint GET; DROP'),
        ]
        for value in bad:
            with self.subTest(value=value[-80:]):
                with self.assertRaises(ValueError):
                    parse_server(value)

    def test_crud_roundtrip_cas_and_persistence(self):
        item, etag = self.create("O'Reilly'; DROP TABLE tasks;--", False)
        self.assertEqual(item["id"], 1)
        self.assertEqual(item["note"], "")
        self.assertIs(item["done"], False)
        code, data, _ = self.request("GET", "/api/tasks", query=b"limit=1&offset=0")
        self.assertEqual((code, len(data["items"])), (200, 1))
        code, data, get_headers = self.request("GET", "/api/tasks/1")
        self.assertEqual(data["item"], item)
        self.assertEqual(get_headers[b"etag"], etag)
        code, data, updated_headers = self.request(
            "PATCH", "/api/tasks/1", {"done": True},
            headers=((b"if-match", etag),))
        self.assertEqual(code, 200)
        self.assertIs(data["item"]["done"], True)
        newer_etag = updated_headers[b"etag"]
        self.assertNotEqual(etag, newer_etag)
        self.assertEqual(self.request(
            "PATCH", "/api/tasks/1", {"done": False},
            headers=((b"if-match", etag),))[0], 409)
        self.assertEqual(self.request(
            "DELETE", "/api/tasks/1", headers=((b"if-match", etag),))[0], 409)
        self.app = make_app(self.output)
        self.assertEqual(self.request("GET", "/api/tasks/1")[1]["item"]["done"], True)
        self.assertEqual(self.request(
            "DELETE", "/api/tasks/1", headers=((b"if-match", newer_etag),))[0], 200)
        self.assertEqual(self.request("GET", "/api/tasks/1")[0], 404)
        self.assertEqual(self.request("GET", "/api/tasks")[:2], (200, {"items": []}))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE name='tasks'").fetchone()[0], 1)

    def test_strict_types_and_source_sql_cannot_inject(self):
        bad = [
            {"title": "x", "done": 1},
            {"title": "x", "done": "false"},
            {"title": "x"},
            {"title": "x", "done": True, "id": 900},
            {"title": "x", "done": True, "unknown": 1},
            {"title": "X" * 161, "done": False},
            {"title": "bad\x00", "done": True},
            {"title": "\ud800", "done": True},
        ]
        for body in bad:
            with self.subTest(body=str(body)[:60]):
                self.assertEqual(self.request("POST", "/api/tasks", body)[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks",
                         raw=b'{"title":"x","title":"y","done":false}')[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks", raw=b'{"title": \xff}')[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks", raw=b"[" + b"1" * 9000 + b"]")[0], 413)
        self.assertEqual(self.request("GET", "/api/tasks/1 OR 1=1")[0], 404)
        self.assertEqual(self.request("GET", "/api/tasks", query=b"limit=1&limit=2")[0], 400)
        self.assertEqual(self.request("GET", "/api/tasks", query=b"limit=100000")[0], 400)
        self.assertEqual(self.request("GET", "/api/tasks", query=b"random=1")[0], 400)
        self.assertEqual(self.request("GET", "/api/tasks")[:2], (200, {"items": []}))

    def test_data_endpoints_fail_closed_without_a_user_identity(self):
        with patch.dict(os.environ, {"SEDRAVA_API_EXPERIMENTAL_ENABLE": "0"}):
            self.assertEqual(self.request("GET", "/api/tasks")[0], 404)
            self.assertEqual(self.request("GET", "/health")[0], 200)
        with patch.dict(os.environ, {"SEDRAVA_API_EXPERIMENTAL_TOKEN": "short"}):
            self.assertEqual(self.request("GET", "/api/tasks")[:2], (503, {"error": "test_token_not_configured"}))
        self.assertEqual(self.request("GET", "/api/tasks", client="192.0.2.1")[0], 403)
        self.assertEqual(self.request("GET", "/api/tasks", server="0.0.0.0")[0], 403)
        self.assertEqual(self.request("GET", "/api/tasks", host=b"public.example")[0], 403)
        self.assertEqual(self.request("GET", "/api/tasks",
                         headers=((b"authorization", b"Bearer fake"),))[0], 400)
        with patch.dict(os.environ, {"SEDRAVA_API_EXPERIMENTAL_TOKEN": "other-test-token-000000000000000000000000"}):
            self.assertEqual(self.request("GET", "/api/tasks")[0], 401)
        self.assertEqual(self.request("OPTIONS", "/api/tasks")[0], 404)
        self.assertEqual(self.request("POST", "/api/tasks", {"title": "x", "done": False},
                         headers=((b"content-type", b"application/json"),))[0], 400)

    def test_preconditions_and_rejected_mutations_do_not_change_database(self):
        item, etag = self.create("unchanged")
        self.assertEqual(self.request("PATCH", "/api/tasks/1", {"done": True})[0], 428)
        self.assertEqual(self.request("DELETE", "/api/tasks/1")[0], 428)
        self.assertEqual(self.request("PATCH", "/api/tasks/1", {},
                                     headers=((b"if-match", etag),))[0], 400)
        self.assertEqual(self.request("PATCH", "/api/tasks/1", {"done": 2},
                                     headers=((b"if-match", etag),))[0], 400)
        self.assertEqual(self.request("PATCH", "/api/tasks/1", {"done": True},
                                     headers=((b"if-match", b'"bogus"'),))[0], 400)
        self.assertEqual(self.request("GET", "/api/tasks/1")[1]["item"], item)

    def test_migration_readiness_and_stale_schema_are_detected(self):
        item, _ = self.create()
        source = SOURCE.replace("title: text(160)", "title: text(150)")
        build_server(source, self.output)
        self.assertEqual(self.request("GET", "/api/tasks")[0], 503)
        self.assertEqual(self.request("GET", "/health")[0], 503)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT title FROM tasks').fetchone()[0], item["title"])


if __name__ == "__main__":
    unittest.main()
