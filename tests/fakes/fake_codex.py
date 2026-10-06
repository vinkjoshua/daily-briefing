#!/usr/bin/env python3
"""Stand-in for the codex CLI, driven by FAKE_CODEX_* environment variables."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEVICE_PROMPT = (
    "Welcome to Codex [v\x1b[90m0.160.0\x1b[0m]\n\n"
    "1. Open this link in your browser and sign in to your account\n"
    "   \x1b[94mhttps://auth.openai.com/codex/device\x1b[0m\n\n"
    "2. Enter this one-time code \x1b[90m(expires in 15 minutes)\x1b[0m\n"
    "   \x1b[94mABCD-12345\x1b[0m\n"
)
UNAUTHORIZED = (
    "ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication"
    " in header, url: https://api.openai.com/v1/responses\n"
)
DEFAULT_REPLY = "# Daily briefing — Test\n\n## Research\nHello\n"


def record(args: list[str], prompt: str = "") -> None:
    log = os.environ.get("FAKE_CODEX_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"args": args, "env": sorted(os.environ), "prompt": prompt}) + "\n")


def logged_in() -> bool:
    auth = Path(os.environ.get("CODEX_HOME", "")) / "auth.json"
    return auth.is_file() and "valid" in auth.read_text(encoding="utf-8")


def main() -> int:
    args = sys.argv[1:]
    if args[:2] == ["login", "--device-auth"]:
        record(args)
        sys.stdout.write(DEVICE_PROMPT)
        sys.stdout.flush()
        time.sleep(0.2)
        if os.environ.get("FAKE_CODEX_LOGIN", "approve") != "approve":
            print("Device code expired")
            return 1
        home = Path(os.environ["CODEX_HOME"])
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth.json").write_text('{"valid": true}', encoding="utf-8")
        print("Successfully logged in")
        return 0
    if args[:1] == ["exec"]:
        prompt = sys.stdin.read()
        record(args, prompt)
        mode = os.environ.get("FAKE_CODEX_EXEC", "auth-file")
        if mode == "hang":
            time.sleep(30)
            return 0
        if mode == "hang-child":
            child = subprocess.Popen(["sleep", "30"])
            Path(os.environ["FAKE_CODEX_PIDFILE"]).write_text(str(child.pid), encoding="utf-8")
            time.sleep(30)
            return 0
        if mode == "fail":
            print("ERROR: stream disconnected before completion")
            return 1
        if mode == "auth-file" and not logged_in():
            sys.stdout.write(UNAUTHORIZED)
            return 1
        if "-o" in args:
            reply = "" if mode == "empty" else os.environ.get("FAKE_CODEX_REPLY", DEFAULT_REPLY)
            Path(args[args.index("-o") + 1]).write_text(reply, encoding="utf-8")
        print("OK")
        return 0
    print(f"fake codex: unsupported args {args}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
