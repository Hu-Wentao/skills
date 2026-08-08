#!/usr/bin/env python3
"""Launch the optional local metrics helper without changing system proxy state."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence


DEFAULT_SERVICE_DIR = Path(
    os.environ.get("WXDOWN_SERVICE_DIR", "~/src/wxdown-service")
).expanduser()


def build_command(service_dir: Path, port: str, websocket_port: str, debug: bool) -> List[str]:
    command = [
        str(service_dir / ".venv" / "bin" / "python"),
        str(service_dir / "main.py"),
        "--port",
        port,
        "--wport",
        websocket_port,
    ]
    if debug:
        command.append("--debug")
    return command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Start the optional wxdown-service helper")
    parser.add_argument("--service-dir", default=str(DEFAULT_SERVICE_DIR))
    parser.add_argument("--port", default="65000", help="local mitmproxy port")
    parser.add_argument("--websocket-port", default="65001")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    service_dir = Path(args.service_dir).expanduser()
    command = build_command(service_dir, args.port, args.websocket_port, args.debug)
    if args.dry_run:
        print(" ".join(command))
        return 0
    if not (service_dir / ".venv" / "bin" / "python").exists():
        print(f"missing service virtualenv: {service_dir / '.venv' / 'bin' / 'python'}", file=sys.stderr)
        return 2
    if not (service_dir / "main.py").exists():
        print(f"missing service entrypoint: {service_dir / 'main.py'}", file=sys.stderr)
        return 2

    child_env = os.environ.copy()
    # Do not let the helper accidentally inherit the user's upstream proxy.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        child_env.pop(key, None)
    return subprocess.call(command, cwd=str(service_dir), env=child_env)


if __name__ == "__main__":
    raise SystemExit(main())
