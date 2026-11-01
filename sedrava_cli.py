"""Command line interface for the experimental Sedrava compiler."""
import argparse
import json
import re
import sys
from pathlib import Path

from sedrava_records import plain, serialize_state, restore_snapshot
from sedrava_core import MAX_SOURCE_CHARS, parse, run, resolve, transition

from sedrava_version import VERSION

def atomic_write_text(path, raw):
    """Replace complete output only after a successful, flushed write."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sedrava", description="Sedrava experimental compiler")
    parser.add_argument("--version", action="version", version=f"sedrava {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Parse and type-check an Sedrava program")
    check.add_argument("source", type=Path)
    execute = commands.add_parser("run", help="Print interpreter state after an optional action sequence")
    execute.add_argument("source", type=Path)
    execute.add_argument("--state-file", type=Path, help="Restore and atomically save accepted persistent state")
    execute.add_argument("actions", nargs="*", help="Actions to execute in order; no wall-clock or UI loop")
    test = commands.add_parser("test", help="Run embedded Sedrava tests")
    test.add_argument("source", type=Path)
    build = commands.add_parser("build", help="Generate an application")
    build.add_argument("target", choices=("web", "android", "api-web", "api-page"))
    build.add_argument("source", type=Path)
    build.add_argument("--output", type=Path)
    build.add_argument("--application-id", help="Stable Android package identity (lowercase reverse-domain name)")
    args = parser.parse_args(argv)
    if args.command == "build" and args.application_id is not None and args.target != "android":
        parser.error("--application-id is only supported for build android")
    try:
        if args.source.stat().st_size > MAX_SOURCE_CHARS * 4:
            raise ValueError("Source exceeds size limit")
        with args.source.open(encoding="utf-8") as handle:
            source = handle.read(MAX_SOURCE_CHARS + 1)
        if args.command == "check":
            if source.lstrip().startswith("service "):
                from sedrava_http_parser import parse_service
                parse_service(source)
            else:
                parse(source)
            print(f"OK: {args.source}")
        elif args.command == "run":
            program = parse(source)
            state = program.states.copy()
            if args.state_file and args.state_file.exists():
                if args.state_file.stat().st_size > 800000: raise ValueError('Snapshot too large')
                raw = args.state_file.read_text(encoding='utf-8')
                state = restore_snapshot(program, raw)
            if program.has_navigation:
                from sedrava_navigation import initial_session, dispatch
                session=initial_session(program,state)
            for action in args.actions:
                if program.has_navigation:
                    session,accepted=dispatch(program,session,action)
                    state=session.state
                else:
                    state, accepted = transition(program, state, action)
                if not accepted:
                    raise ValueError(f"Action {action}: invariant rejected; state unchanged")
            if args.state_file:
                atomic_write_text(args.state_file, serialize_state(program, state))
            result={k:plain(v) for k,v in resolve(state,program.derived).items()}
            if program.has_navigation: result={"state":result,"stack":list(session.stack)}
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        elif args.command == "test":
            count = run(parse(source))
            print(f"PASS: {count} Sedrava tests")
        elif args.command == "build" and args.target == "api-web":
            from sedrava_http_parser import parse_service
            from sedrava_http_codegen import generate_fetch_module
            service, schema = parse_service(source)
            output = args.output or Path("build/api-web/service.mjs")
            if output.resolve() == args.source.resolve():
                raise ValueError("API output must differ from the source file")
            atomic_write_text(output, generate_fetch_module(service, schema))
            print(output)
        elif args.command == "build" and args.target == "api-page":
            from sedrava_http_parser import parse_service
            from sedrava_http_codegen import generate_fetch_module
            from sedrava_http_page import generate_api_page
            service, schema = parse_service(source)
            output = args.output or Path("build/api-page")
            html_path = output / "index.html"
            module_path = output / "service.mjs"
            if output.exists() and not output.is_dir():
                raise ValueError("API page output must be a directory")
            if html_path.resolve() == args.source.resolve() or module_path.resolve() == args.source.resolve():
                raise ValueError("API page output must differ from the source file")
            module = generate_fetch_module(service, schema)
            page = generate_api_page(service, schema)
            atomic_write_text(module_path, module)
            atomic_write_text(html_path, page)
            print(html_path)
        elif args.target == "web":
            from web_codegen import generate
            output = args.output or Path("build/web/index.html")
            result = generate(source)
            if output.resolve() == args.source.resolve():
                raise ValueError("Web output must differ from the source file")
            atomic_write_text(output, result)
            print(output)
        else:
            from android_codegen_v03 import generate
            output = args.output or Path("build/generated-android")
            print(generate(source, output, application_id=args.application_id))
        return 0
    except (OSError, ValueError, AssertionError, RecursionError) as exc:
        message = str(exc)
        match = re.match(r"Line (\d+): (?:column (\d+): )?(.*)", message)
        if match:
            print(f"{args.source}:{match.group(1)}:{match.group(2) or 1}: error: {match.group(3)}", file=sys.stderr)
        else:
            print(f"sedrava: {args.source}: {message}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
