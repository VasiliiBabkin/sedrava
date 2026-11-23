#!/usr/bin/env python3
"""Real Chromium acceptance for already-validated 0.11 stable / 0.12 native builds.

Designed to run on a separate, disposable browser machine after transferring
ONLY generated static fixtures. Requires local Playwright + Chromium. It
imports the existing interactive acceptance actions without rebuilding source.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import sys
from threading import Thread

from playwright.sync_api import sync_playwright,expect
import verify_native_web_011 as actions

CASES={
    "platform_site":"site",
    "web_ui_011_landing":"site",
    "platform_catalog":"webapp",
    "platform_crm":"webapp",
    "platform_tasks":"webapp",
    "webapp_011_counter":"webapp",
    "webapp_011_tasks":"webapp",
}

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*_):
        pass


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True,
                    help="Folder containing stable011/<example> and native012/<example>")
    ap.add_argument("--chromium",type=str,default="/usr/bin/chromium")
    ap.add_argument("--report",type=Path)
    args=ap.parse_args()
    root=args.root.resolve()
    for backend in ("stable011","native012"):
        for case in CASES:
            assert (root/backend/case/"index.html").is_file(),(backend,case)
    server=ThreadingHTTPServer(
        ("127.0.0.1",0),partial(QuietHandler,directory=str(root))
    )
    worker=Thread(target=server.serve_forever,daemon=True)
    worker.start()
    checks=[]
    try:
        origin=f"http://127.0.0.1:{server.server_port}"
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(
                executable_path=args.chromium,headless=True,args=["--no-sandbox"]
            )
            try:
                for backend in ("stable011","native012"):
                    for case,mode in CASES.items():
                        with browser.new_context() as context:
                            page=context.new_page()
                            failures=[]
                            requests=[]
                            page.on("pageerror",lambda error:failures.append(str(error)))
                            page.on("request",lambda req:requests.append(req.url))
                            response=page.goto(
                                f"{origin}/{backend}/{case}/index.html",
                                wait_until="load",timeout=30000
                            )
                            assert response is not None and response.ok,(backend,case)
                            if mode=="site":
                                actions.site_view(page,case=="platform_site")
                            elif case=="platform_catalog":
                                assert page.locator("script[src='app.js']").count()==1
                                expect(page.get_by_role("heading").first).to_be_visible()
                                assert page.locator("main").count()==1
                            else:
                                assert page.locator("script[src='app.js']").count()==1
                                assert page.locator("script:not([src])").count()==0
                                {
                                    "webapp_011_counter":actions.counter,
                                    "webapp_011_tasks":actions.tasks,
                                    "platform_tasks":actions.routed_tasks,
                                    "platform_crm":actions.crm,
                                }[case](page)
                            assert not failures,(backend,case,failures)
                            assert all(url.startswith(origin+"/") for url in requests),(backend,case,requests)
                            checks.append({
                                "engine":backend,"source":case,
                                "result":"PASS","requests":len(requests),
                                "page_errors":0,
                            })
                            print(f"PASS Chromium {browser.version} {backend} {case}",flush=True)
                result={
                    "schema":"sedrava.native.stable011.real-browser.v1",
                    "browser":"Chromium",
                    "browser_version":browser.version,
                    "browser_executable":args.chromium,
                    "transport":"local loopback static HTML/CSS/JS",
                    "engines":["stable011","native012"],
                    "cases":checks,
                    "total_passed":len(checks),
                    "result":"PASS",
                    "limitations":"Isolated Linux Chromium browser on generated static fixtures; no Android device, Firefox/WebKit or user production data.",
                }
                if args.report:
                    args.report.parent.mkdir(parents=True,exist_ok=True)
                    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
                print(f"PASS {len(checks)} real Chromium scenarios",flush=True)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__=="__main__":
    sys.exit(main())
