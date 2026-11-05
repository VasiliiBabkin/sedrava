"""Real loopback HTTP smoke against generated ASGI via uvicorn and SQLite.

Runs only in experimental CI; never contacts a public interface or external API.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]


def call(url, method="GET", payload=None, *, token=None, etag=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if etag is not None:
        headers["If-Match"] = etag
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response), response.headers
    except error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode()), exc.headers
        finally:
            exc.close()


def main():
    from sedrava_server_schema import build_server
    from sedrava_server_runtime import migrate_database
    with tempfile.TemporaryDirectory(prefix="sedrava-a2-http-") as temp:
        root = Path(temp)
        target = root / "generated"
        source = (ROOT / "examples/server_013_api_tasks.sdr").read_text(encoding="utf-8")
        build_server(source, target)
        db = root / "local.sqlite"
        token = secrets.token_urlsafe(48)
        env = os.environ.copy()
        env.update({
            "SEDRAVA_DB_PATH": str(db),
            "SEDRAVA_API_EXPERIMENTAL_ENABLE": "1",
            "SEDRAVA_API_EXPERIMENTAL_TOKEN": token,
            "PYTHONNOUSERSITE": "1",
        })
        old = os.environ.get("SEDRAVA_DB_PATH")
        os.environ["SEDRAVA_DB_PATH"] = str(db)
        try:
            assert migrate_database(target)["schema_version"] == 2
        finally:
            if old is None:
                os.environ.pop("SEDRAVA_DB_PATH", None)
            else:
                os.environ["SEDRAVA_DB_PATH"] = old
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_probe:
            socket_probe.bind(("127.0.0.1", 0))
            port = socket_probe.getsockname()[1]
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
             "--port", str(port), "--no-access-log", "--log-level", "error"],
            cwd=target, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if server.poll() is not None:
                    raise AssertionError("ASGI server terminated before readiness")
                try:
                    status, _, _ = call(base + "/health")
                    if status == 200:
                        break
                except (error.URLError, TimeoutError, ConnectionError):
                    time.sleep(0.1)
            else:
                raise AssertionError("ASGI health endpoint did not start")
            status, _, _ = call(base + "/api/tasks")
            assert status == 401, "No bearer token should be refused"
            status, data, _ = call(
                base + "/api/tasks", "POST",
                {"title": "Real HTTP + SQLite", "done": False}, token=token)
            assert status == 201 and data["item"]["id"] == 1, (status, data)
            status, data, headers = call(base + "/api/tasks/1", token=token)
            assert status == 200 and data["item"]["title"] == "Real HTTP + SQLite"
            etag = headers["ETag"]
            status, data, headers = call(
                base + "/api/tasks/1", "PATCH", {"done": True},
                token=token, etag=etag)
            assert status == 200 and data["item"]["done"] is True
            status, data, _ = call(
                base + "/api/tasks/1", "DELETE", token=token, etag=etag)
            assert status == 409 and data == {"error": "conflict"}
            status, data, _ = call(
                base + "/api/tasks/1", "DELETE", token=token, etag=headers["ETag"])
            assert status == 200 and data == {"deleted": True, "id": 1}
            status, data, _ = call(base + "/api/tasks?limit=20", token=token)
            assert status == 200 and data == {"items": []}
            print("PASS: real ASGI HTTP + SQLite CRUD, token refusal and stale ETag conflict")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
