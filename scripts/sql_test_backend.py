"""Explicit test backend selection; defaults to original NativeLog tests."""
import os
from pathlib import Path

BACKEND = os.environ.get("SEDRAVA_SQL_TEST_BACKEND", "native-log")
if BACKEND not in ("native-log", "cow"):
    raise ValueError("SEDRAVA_SQL_TEST_BACKEND must be native-log or cow")

def db_command(command):
    return "cow-" + command if BACKEND == "cow" else command

def backend_args():
    return ["--backend", BACKEND] if BACKEND == "cow" else []

def database_bytes(path):
    path = Path(path)
    data = path.read_bytes()
    if BACKEND == "cow":
        data += path.with_name(path.name + ".head").read_bytes()
    return data
