"""Experimental 0.13 server/SQLite/migration acceptance with actual SQLite files."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sedrava_server_schema import parse_server, build_server, load_manifest
from sedrava_server_runtime import (MigrationError, migrate_database, verify_database,
                                    backup_database, make_app)

V1 = '''server "Taskboard"
database sqlite env SEDRAVA_013_TEST_DB
migration 1:
    create table tasks:
        title: text(160)
        done: bool
'''
V2 = V1 + '''migration 2:
    add column tasks.note: text(300) default ""
'''
V3 = V2 + '''migration 3:
    add column tasks.count: int default 0
'''


class ServerSchema013Tests(unittest.TestCase):
    def test_parser_schema_contract_and_no_execution(self):
        doc = parse_server(V3)
        self.assertEqual(doc["db_env"], "SEDRAVA_013_TEST_DB")
        self.assertEqual([m["version"] for m in doc["migrations"]], [1, 2, 3])
        self.assertEqual([f["name"] for f in doc["tables"]["tasks"]],
                         ["title", "done", "note", "count"])
        self.assertEqual(doc["migrations"][1]["operations"][0]["field"]["default"], "")

    def test_fail_closed_migration_syntax(self):
        cases = [
            V1.replace("migration 1:", "migration 2:"),
            V1.replace("tasks:", "sedrava_migrations:"),
            V1.replace("tasks:", "tasks; DROP TABLE users:"),
            V1.replace("title: text(160)", "title: text(9999)"),
            V1.replace("    create table tasks:", "    execute SQL DELETE FROM tasks"),
            V1.replace("    create table tasks:", "    create table tasks:\n        id: int"),
            V1.replace("title: text(160)", "title: text(160) default \"hi\""),
            V2.replace('default ""', "default 'invalid'"),
            V2.replace("migration 2:", "migration 1:"),
            V2.replace("text(300) default \"\"", "text(1) default \"long\""),
            V1.replace("database sqlite", "database postgres"),
            V1.replace("    create", "\tcreate"),
        ]
        for source in cases:
            with self.subTest(source=source[-75:]):
                with self.assertRaises(ValueError):
                    parse_server(source)

    def test_generated_files_are_stable_and_not_source_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tasks.sdr"
            source.write_text(V2)
            target = root / "generated"
            first = build_server(source.read_text(), target, source)
            self.assertEqual(first, target / "server.py")
            before = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
            build_server(source.read_text(), target, source)
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()})
            self.assertEqual(load_manifest(target), parse_server(V2))
            (target / "schema.json").write_text("{}")
            with self.assertRaises(ValueError):
                load_manifest(target)
            with self.assertRaises(ValueError):
                build_server(V1, target, target / "server.py")


class ServerSQLite013Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "generated"
        self.db = self.root / "test.db"
        self.env = patch.dict(os.environ, {"SEDRAVA_013_TEST_DB": str(self.db)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def compile(self, source):
        build_server(source, self.output)

    def test_explicit_migrations_durability_and_rejected_downgrade(self):
        self.compile(V1)
        with self.assertRaises(MigrationError):
            make_app(self.output)
        self.assertEqual(migrate_database(self.output)["schema_version"], 1)
        self.assertEqual(migrate_database(self.output)["schema_version"], 1)
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO tasks(title, done) VALUES (?, ?)", ("Before upgrade", 0))
        self.compile(V2)
        with self.assertRaises(MigrationError):
            verify_database(self.output)
        self.assertEqual(migrate_database(self.output)["schema_version"], 2)
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT title, done, note FROM tasks").fetchone()
        self.assertEqual(row, ("Before upgrade", 0, ""))
        self.compile(V1)
        with self.assertRaisesRegex(MigrationError, "newer"):
            verify_database(self.output)
        with self.assertRaisesRegex(MigrationError, "newer"):
            migrate_database(self.output)

    def test_hash_tamper_is_rejected_without_mutating_data(self):
        self.compile(V1)
        migrate_database(self.output)
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO tasks(title,done) VALUES (?,?)", ("kept", 1))
        self.compile(V1.replace("title: text(160)", "title: text(150)"))
        with self.assertRaisesRegex(MigrationError, "changed"):
            migrate_database(self.output)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT title FROM tasks").fetchone()[0], "kept")

    def test_failed_migration_rolls_back_all_ddl(self):
        self.compile(V1)
        migrate_database(self.output)
        # Induce an external conflicting table so the second migration fails.
        with sqlite3.connect(self.db) as c:
            c.execute("ALTER TABLE tasks ADD COLUMN note TEXT")
        self.compile(V2)
        with self.assertRaises((sqlite3.DatabaseError, MigrationError)):
            migrate_database(self.output)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT MAX(version) FROM "_sedrava_migrations"').fetchone()[0], 1)

    def test_backup_and_restore_are_real_and_non_overwriting(self):
        self.compile(V1)
        migrate_database(self.output)
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO tasks(title,done) VALUES (?,?)", ("persisted", 1))
        target = self.root / "backup.sqlite"
        receipt = backup_database(self.output, target)
        self.assertEqual(len(receipt["sha256"]), 64)
        with sqlite3.connect(target) as c:
            self.assertEqual(c.execute("SELECT title FROM tasks").fetchone()[0], "persisted")
        with self.assertRaises(MigrationError):
            backup_database(self.output, target)
        self.compile(V2)
        migrate_database(self.output)
        with self.assertRaises(MigrationError):
            # Backup should also refuse a source path as its own destination.
            backup_database(self.output, self.db)
        # Test restore on a separate file after disconnecting the original DB.
        os.environ["SEDRAVA_013_TEST_DB"] = str(target)
        self.compile(V1)
        self.assertEqual(verify_database(self.output)["schema_version"], 1)

    def test_health_asgi_and_absence_of_unprotected_data_routes(self):
        self.compile(V1)
        migrate_database(self.output)
        app = make_app(self.output)
        async def request(path, method="GET"):
            sent = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                sent.append(message)
            await app({"type": "http", "path": path, "method": method}, receive, send)
            return sent
        health = asyncio.run(request("/health"))
        self.assertEqual(health[0]["status"], 200)
        self.assertEqual(json.loads(health[1]["body"])["schema_version"], 1)
        self.assertEqual(asyncio.run(request("/api/tasks"))[0]["status"], 404)
        self.assertEqual(asyncio.run(request("/health", "POST"))[0]["status"], 404)
        self.compile(V2)
        self.assertEqual(asyncio.run(request("/health"))[0]["status"], 503)

    def test_db_location_requires_absolute_path_and_no_symlink(self):
        self.compile(V1)
        with patch.dict(os.environ, {"SEDRAVA_013_TEST_DB": "relative.sqlite"}):
            with self.assertRaises(MigrationError):
                migrate_database(self.output)
        link = self.root / "link.sqlite"
        self.db.write_bytes(b"")
        link.symlink_to(self.db)
        with patch.dict(os.environ, {"SEDRAVA_013_TEST_DB": str(link)}):
            with self.assertRaises(MigrationError):
                migrate_database(self.output)


if __name__ == "__main__":
    unittest.main()
