#!/usr/bin/env python3
"""Read-only environment check for batch-download-wechat-data."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_EXPORTER = Path(
    os.environ.get("WECHAT_ARTICLE_EXPORTER_DIR", "~/src/wechat-article-exporter")
).expanduser()
DEFAULT_METRICS_SERVICE = Path(
    os.environ.get("WXDOWN_SERVICE_DIR", "~/src/wxdown-service")
).expanduser()


def which(name: str) -> str:
    return shutil.which(name) or ""


def run_read_only(command: List[str], timeout: int = 5) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "output": (completed.stdout or completed.stderr or "").strip(),
    }


def package_version(path: Path) -> str:
    package_json = path / "package.json"
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("version") or "") if isinstance(payload, dict) else ""


def proxy_state() -> Dict[str, Any]:
    if platform.system() != "Darwin" or not which("networksetup"):
        return {"supported": False}
    services_result = run_read_only(["networksetup", "-listallnetworkservices"])
    services: List[str] = []
    if services_result.get("ok"):
        for line in str(services_result.get("output") or "").splitlines():
            line = line.strip()
            if line and not line.startswith("An asterisk") and not line.startswith("*"):
                services.append(line)
    service = "Wi-Fi" if "Wi-Fi" in services else (services[0] if services else "")
    if not service:
        return {"supported": True, "error": "no network service found"}
    web = run_read_only(["networksetup", "-getwebproxy", service])
    secure = run_read_only(["networksetup", "-getsecurewebproxy", service])
    return {
        "supported": True,
        "service": service,
        "web_proxy": web.get("output", ""),
        "secure_web_proxy": secure.get("output", ""),
    }


def network_check(base_url: str) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/"
    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "batch-download-wechat-data-doctor/1.0"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"ok": True, "url": url, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "url": url, "status": exc.code, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def build_report(
    exporter_path: Path,
    metrics_path: Path,
    api_base: str,
    check_network: bool,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "commands": {
            name: which(name)
            for name in (
                "python3",
                "node",
                "corepack",
                "yarn",
                "mitmdump",
                "security",
                "networksetup",
            )
        },
        "paths": {
            "exporter": {
                "path": str(exporter_path),
                "exists": exporter_path.exists(),
                "package_json": (exporter_path / "package.json").exists(),
                "version": package_version(exporter_path),
            },
            "metrics_service": {
                "path": str(metrics_path),
                "exists": metrics_path.exists(),
                "main_py": (metrics_path / "main.py").exists(),
                "requirements": (metrics_path / "requirements.txt").exists(),
            },
        },
        "proxy_state": proxy_state(),
        "manual_required": [
            "User scans the exporter QR code and selects the intended account.",
            "User opens WeChat desktop pages when credential capture is needed.",
            "User confirms certificate trust or system proxy changes.",
            "Fresh credentials are required for metrics and comments.",
        ],
        "hard_limits": [
            "The skill cannot operate WeChat UI.",
            "The skill cannot bypass login, paywalls, private/deleted content, or permissions.",
            "Metrics may fail when credentials expire or comments are hidden.",
        ],
    }
    if check_network:
        report["network"] = network_check(api_base)

    baseline_ok = bool(report["commands"]["python3"])
    network_ok = not check_network or bool(report["network"].get("ok"))
    report["ok"] = baseline_ok and network_ok
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only environment check")
    parser.add_argument("--exporter-path", default=str(DEFAULT_EXPORTER))
    parser.add_argument("--metrics-path", default=str(DEFAULT_METRICS_SERVICE))
    parser.add_argument("--api-base", default="https://down.mptext.top")
    parser.add_argument("--check-network", action="store_true")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    report = build_report(
        Path(args.exporter_path).expanduser(),
        Path(args.metrics_path).expanduser(),
        args.api_base,
        args.check_network,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
