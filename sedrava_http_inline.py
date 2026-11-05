"""Split an optional trailing API0 service from a regular Sedrava application.

The API declaration is kept out of the deterministic app parser and runtime.
"""
import re

SERVICE_HEADER = re.compile(r"^service [A-Za-z][A-Za-z0-9_]{0,63}:$")


def split_app_service(source: str):
    if type(source) is not str:
        raise ValueError("Expected Sedrava source text")
    lines = source.splitlines(keepends=True)
    headers = [i for i, line in enumerate(lines)
               if SERVICE_HEADER.fullmatch(line.rstrip("\r\n"))]
    if not headers:
        return source, None
    if len(headers) != 1 or headers[0] == 0:
        raise ValueError("Exactly one trailing service declaration is allowed after the application")
    offset = headers[0]
    app = "".join(lines[:offset]).rstrip() + "\n"
    service = "".join(lines[offset:])
    from sedrava_http_display import parse_display_service as parse_service
    parse_service(service)
    return app, service
