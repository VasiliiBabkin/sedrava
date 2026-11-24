"""Explicit test-only oracle; no old compiler is part of the Rust distribution."""
import os
from pathlib import Path

def legacy_root():
    raw = os.environ.get("SEDRAVA_LEGACY_ROOT")
    if not raw:
        raise RuntimeError("Historical comparison requires SEDRAVA_LEGACY_ROOT: extract the v0.12.0-alpha.1 source tree into a separate directory; see docs/HISTORY.md.")
    root = Path(raw).resolve()
    if not (root / "sedrava_cli.py").is_file():
        raise RuntimeError("Missing historical reference sedrava_cli.py")
    return root
