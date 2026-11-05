"""Structured, stable external error envelopes for the experimental Sedrava CLI.

No traceback is exposed for user input failures. Existing human CLI errors stay
the default; JSON diagnostics are opt-in and include source positions when known.
"""
from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class Diagnostic:
    code: str
    phase: str
    message: str
    source: str
    line: int | None = None
    column: int | None = None

    def as_dict(self):
        return {
            "code": self.code,
            "phase": self.phase,
            "message": self.message,
            "location": {
                "source": self.source,
                "line": self.line,
                "column": self.column,
            },
        }


class SedravaError(ValueError):
    """Optional typed error for compiler passes to refine in future releases."""

    def __init__(self, code, message, *, phase="compile", line=None, column=None):
        if not re.fullmatch(r"SDR-E[0-9]{4}", code):
            raise ValueError("Invalid Sedrava diagnostic code")
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.line = line
        self.column = column


def from_exception(exc, source, command, *, phase=None):
    from sedrava_source_map import LocatedError
    if isinstance(exc,LocatedError):
        return Diagnostic("SDR-E2001" if phase=="execute" else "SDR-E1001",phase or "compile",exc.message,exc.source,exc.line,exc.column)
    if isinstance(exc, SedravaError):
        return Diagnostic(exc.code, exc.phase, str(exc), str(source), exc.line, exc.column)
    match = re.match(r"^Line ([1-9][0-9]*): (?:column ([1-9][0-9]*): )?(.*)", str(exc), re.S)
    line = int(match[1]) if match else None
    column = int(match[2] or 1) if match else None
    message = match[3] if match else str(exc)
    if isinstance(exc, OSError):
        return Diagnostic("SDR-E3001", "io", message, str(getattr(exc,"filename",None) or source), line, column)
    if isinstance(exc, AssertionError):
        return Diagnostic("SDR-E4001", "test", message, str(source), line, column)
    if phase == "execute" or (phase is None and command in ("run", "test")):
        return Diagnostic("SDR-E2001", "execute", message, str(source), line, column)
    return Diagnostic("SDR-E1001", "compile", message, str(source), line, column)
