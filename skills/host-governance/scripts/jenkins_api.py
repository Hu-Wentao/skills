#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Secret-safe Jenkins job API adapter for governed host workflows."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class JenkinsError(RuntimeError):
    """A sanitized Jenkins operation failure."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def redact(value: str) -> str:
    value = re.sub(
        r"(https?://)[^/@\s:]+:[^/@\s]+@",
        r"\1[REDACTED]@",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"(?i)(authorization\s*:\s*)(?:basic|bearer)\s+\S+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)\b(password|passwd|token|secret|webhook|api[_-]?key)\b"
        r"(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        value,
    )
    return value


def job_path(full_name: str) -> str:
    parts = [part for part in full_name.strip("/").split("/") if part]
    if not parts:
        raise JenkinsError("job name must not be empty")
    return "".join(f"/job/{urllib.parse.quote(part, safe='')}" for part in parts)


def view_path(name: str) -> str:
    parts = [part for part in name.strip("/").split("/") if part]
    if not parts:
        raise JenkinsError("view name must not be empty")
    return "".join(f"/view/{urllib.parse.quote(part, safe='')}" for part in parts)


def parse_params(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise JenkinsError(f"parameter must use NAME=VALUE syntax: {item!r}")
        name, value = item.split("=", 1)
        if not name:
            raise JenkinsError("parameter name must not be empty")
        if name in result:
            raise JenkinsError(f"duplicate build parameter: {name}")
        result[name] = value
    return result


def _node_text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    value = node.findtext(path)
    return value.strip() if value is not None else None


def config_summary(raw: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise JenkinsError(f"invalid Jenkins config XML: {exc}") from exc

    parameters: list[dict[str, Any]] = []
    for node in root.findall(".//parameterDefinitions/*"):
        choices = [
            text.strip()
            for text in (choice.text for choice in node.findall(".//choices//string"))
            if text and text.strip()
        ]
        parameters.append(
            {
                "type": node.tag.rsplit("}", 1)[-1],
                "name": _node_text(node, "name"),
                "default": _node_text(node, "defaultValue")
                or _node_text(node, "defaultParameterValue/value"),
                "choices": choices,
            }
        )

    builders: list[dict[str, Any]] = []
    builders_node = root.find("builders")
    if builders_node is not None:
        for node in list(builders_node):
            command = _node_text(node, "command")
            builders.append(
                {
                    "type": node.tag.rsplit("}", 1)[-1],
                    "command_sha256": (
                        hashlib.sha256(command.encode("utf-8")).hexdigest()
                        if command is not None
                        else None
                    ),
                    "command_line_count": len(command.splitlines()) if command else 0,
                }
            )

    wrappers_node = root.find("buildWrappers")
    publishers_node = root.find("publishers")
    return {
        "config_sha256": sha256_bytes(raw),
        "root_type": root.tag.rsplit("}", 1)[-1],
        "disabled": _node_text(root, "disabled"),
        "can_roam": _node_text(root, "canRoam"),
        "assigned_node": _node_text(root, "assignedNode"),
        "concurrent_build": _node_text(root, "concurrentBuild"),
        "parameters": parameters,
        "builders": builders,
        "wrappers": (
            [node.tag.rsplit("}", 1)[-1] for node in list(wrappers_node)]
            if wrappers_node is not None
            else []
        ),
        "publishers": (
            [node.tag.rsplit("}", 1)[-1] for node in list(publishers_node)]
            if publishers_node is not None
            else []
        ),
    }


def require_authorized(value: bool) -> None:
    if not value:
        raise JenkinsError("mutation refused: pass --authorized after user authorization")


class JenkinsClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        token: str,
        *,
        ca_bundle: str | None = None,
        request_timeout: float = 30.0,
    ) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise JenkinsError("Jenkins URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise JenkinsError("Jenkins URL must not contain credentials")
        self.base_url = base_url.rstrip("/")
        self.base_path = parsed.path.rstrip("/")
        self.request_timeout = request_timeout
        self._auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

        context = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=context),
        )
        self._crumb: tuple[str, str] | None | object = _UNSET

    def _url(self, path: str) -> str:
        return self.base_url + "/" + path.lstrip("/")

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> urllib.response.addinfourl:
        request_headers = {"Authorization": self._auth}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self._url(path), data=data, headers=request_headers, method=method
        )
        try:
            response = self._opener.open(request, timeout=self.request_timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read(2048).decode("utf-8", "replace")
            raise JenkinsError(
                redact(f"Jenkins HTTP {exc.code} for {path}: {body[:1000]}")
            ) from None
        except urllib.error.URLError as exc:
            raise JenkinsError(redact(f"Jenkins request failed for {path}: {exc.reason}")) from None
        if response.status not in expected:
            response.close()
            raise JenkinsError(f"unexpected Jenkins HTTP {response.status} for {path}")
        return response

    def get_bytes(self, path: str) -> bytes:
        with self._request(path) as response:
            return response.read()

    def get_json(self, path: str) -> dict[str, Any]:
        raw = self.get_bytes(path)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JenkinsError(f"Jenkins returned invalid JSON for {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise JenkinsError(f"Jenkins returned non-object JSON for {path}")
        return value

    def _crumb_header(self) -> dict[str, str]:
        if self._crumb is _UNSET:
            try:
                value = self.get_json("/crumbIssuer/api/json")
                field = value.get("crumbRequestField")
                crumb = value.get("crumb")
                self._crumb = (str(field), str(crumb)) if field and crumb else None
            except JenkinsError as exc:
                if "HTTP 404" in str(exc):
                    self._crumb = None
                else:
                    raise
        if self._crumb is None:
            return {}
        field, crumb = self._crumb
        return {field: crumb}

    def post(
        self,
        path: str,
        *,
        data: bytes = b"",
        content_type: str | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> urllib.response.addinfourl:
        headers = self._crumb_header()
        if content_type:
            headers["Content-Type"] = content_type
        return self._request(
            path,
            method="POST",
            data=data,
            headers=headers,
            expected=expected,
        )

    def path_from_location(self, location: str) -> str:
        path = urllib.parse.urlsplit(location).path
        if self.base_path and path.startswith(self.base_path + "/"):
            path = path[len(self.base_path) :]
        return path


_UNSET = object()


def inspect_job(client: JenkinsClient, job: str) -> dict[str, Any]:
    path = job_path(job)
    metadata = client.get_json(
        path
        + "/api/json?tree=name,color,buildable,inQueue,nextBuildNumber,"
        + "lastBuild[number,result,duration]"
    )
    config = client.get_bytes(path + "/config.xml")
    last = metadata.get("lastBuild")
    if isinstance(last, dict) and last.get("number") is not None:
        last = dict(last)
        last["url"] = f"{client.base_url}{path}/{last['number']}/"
    return {
        "job": metadata.get("name") or job,
        "url": f"{client.base_url}{path}/",
        "color": metadata.get("color"),
        "buildable": metadata.get("buildable"),
        "in_queue": metadata.get("inQueue"),
        "next_build_number": metadata.get("nextBuildNumber"),
        "last_build": last,
        "config": config_summary(config),
    }


def compare_jobs(client: JenkinsClient, reference: str, target: str) -> dict[str, Any]:
    reference_info = inspect_job(client, reference)
    target_info = inspect_job(client, target)
    reference_config = reference_info["config"]
    target_config = target_info["config"]
    fields = [
        "root_type",
        "disabled",
        "can_roam",
        "assigned_node",
        "concurrent_build",
        "parameters",
        "builders",
        "wrappers",
        "publishers",
    ]
    differences = {
        field: {"reference": reference_config[field], "target": target_config[field]}
        for field in fields
        if reference_config[field] != target_config[field]
    }
    return {
        "reference": reference_info,
        "target": target_info,
        "structural_differences": differences,
    }


def write_private_snapshot(path: Path, raw: bytes) -> None:
    path = path.expanduser().resolve(strict=False)
    if not path.parent.is_dir():
        raise JenkinsError(f"snapshot parent directory does not exist: {path.parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise JenkinsError(f"snapshot path already exists: {path}") from None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def read_config(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise JenkinsError(f"config input must be a regular non-symlink file: {path}")
    raw = path.read_bytes()
    config_summary(raw)
    return raw


def create_config(client: JenkinsClient, job: str, raw: bytes, parent: str | None) -> dict[str, Any]:
    if "/" in job or not job:
        raise JenkinsError("config-create --job must be one job name; use --parent for folders")
    container = job_path(parent) if parent else ""
    path = container + "/createItem?" + urllib.parse.urlencode({"name": job})
    with client.post(path, data=raw, content_type="application/xml"):
        pass
    full_name = f"{parent.strip('/')}/{job}" if parent else job
    return inspect_job(client, full_name)


def update_config(
    client: JenkinsClient, job: str, raw: bytes, expected_current_sha256: str
) -> dict[str, Any]:
    path = job_path(job)
    current = client.get_bytes(path + "/config.xml")
    actual = sha256_bytes(current)
    if actual != expected_current_sha256.lower():
        raise JenkinsError(
            f"config changed since snapshot: expected {expected_current_sha256}, actual {actual}"
        )
    with client.post(path + "/config.xml", data=raw, content_type="application/xml"):
        pass
    updated = client.get_bytes(path + "/config.xml")
    expected_updated = sha256_bytes(raw)
    actual_updated = sha256_bytes(updated)
    if actual_updated != expected_updated:
        raise JenkinsError(
            f"Jenkins config read-back mismatch: submitted {expected_updated}, returned {actual_updated}"
        )
    return inspect_job(client, job)


def trigger_build(
    client: JenkinsClient,
    job: str,
    params: dict[str, str],
    *,
    wait: bool,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    path = job_path(job)
    endpoint = path + ("/buildWithParameters" if params else "/build")
    data = urllib.parse.urlencode(params).encode("utf-8") if params else b""
    with client.post(
        endpoint,
        data=data,
        content_type="application/x-www-form-urlencoded",
        expected=(200, 201, 202),
    ) as response:
        location = response.headers.get("Location")
    if not location:
        raise JenkinsError("Jenkins trigger response did not include a queue Location")
    queue_path = client.path_from_location(location).rstrip("/") + "/"
    result: dict[str, Any] = {
        "job": job,
        "queue_url": client.base_url + queue_path,
        "parameter_names": sorted(params),
    }
    if not wait:
        result["status"] = "queued"
        return result

    deadline = time.monotonic() + timeout
    build_number: int | None = None
    while time.monotonic() < deadline:
        queue = client.get_json(queue_path + "api/json")
        if queue.get("cancelled"):
            raise JenkinsError("queued build was cancelled")
        executable = queue.get("executable")
        if isinstance(executable, dict) and executable.get("number") is not None:
            build_number = int(executable["number"])
            break
        time.sleep(poll_interval)
    if build_number is None:
        raise JenkinsError("timed out waiting for a Jenkins executor")

    build_api = f"{path}/{build_number}/api/json?tree=building,result,duration,estimatedDuration"
    while time.monotonic() < deadline:
        build = client.get_json(build_api)
        if not build.get("building"):
            result.update(
                {
                    "status": "completed",
                    "build_number": build_number,
                    "result": build.get("result"),
                    "duration_ms": build.get("duration"),
                    "estimated_duration_ms": build.get("estimatedDuration"),
                    "build_url": f"{client.base_url}{path}/{build_number}/",
                }
            )
            return result
        time.sleep(poll_interval)
    raise JenkinsError(f"timed out waiting for Jenkins build {build_number}")


def _client_from_args(args: argparse.Namespace) -> JenkinsClient:
    url = os.environ.get(args.url_env)
    user = os.environ.get(args.user_env)
    token = os.environ.get(args.token_env)
    if not url:
        raise JenkinsError(f"missing Jenkins URL environment variable: {args.url_env}")
    if not user:
        raise JenkinsError(f"missing Jenkins user environment variable: {args.user_env}")
    if not token:
        raise JenkinsError(f"missing Jenkins token environment variable: {args.token_env}")
    ca_bundle = os.environ.get(args.ca_bundle_env) if args.ca_bundle_env else None
    return JenkinsClient(
        url,
        user,
        token,
        ca_bundle=ca_bundle,
        request_timeout=args.request_timeout,
    )


def _print(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url-env", default="JENKINS_URL")
    parser.add_argument("--user-env", default="JENKINS_USER")
    parser.add_argument("--token-env", default="JENKINS_API_TOKEN")
    parser.add_argument("--ca-bundle-env", default="JENKINS_CA_BUNDLE")
    parser.add_argument("--request-timeout", type=float, default=30.0)
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--job", required=True)

    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--reference-job", required=True)
    compare_parser.add_argument("--target-job", required=True)

    get_parser = commands.add_parser("config-get")
    get_parser.add_argument("--job", required=True)
    get_parser.add_argument("--output", type=Path, required=True)

    create_parser = commands.add_parser("config-create")
    create_parser.add_argument("--job", required=True)
    create_parser.add_argument("--parent")
    create_parser.add_argument("--input", type=Path, required=True)
    create_parser.add_argument("--authorized", action="store_true")

    update_parser = commands.add_parser("config-update")
    update_parser.add_argument("--job", required=True)
    update_parser.add_argument("--input", type=Path, required=True)
    update_parser.add_argument("--expected-current-sha256", required=True)
    update_parser.add_argument("--authorized", action="store_true")

    view_parser = commands.add_parser("view-add")
    view_parser.add_argument("--view", required=True)
    view_parser.add_argument("--job", required=True)
    view_parser.add_argument("--authorized", action="store_true")

    trigger_parser = commands.add_parser("trigger")
    trigger_parser.add_argument("--job", required=True)
    trigger_parser.add_argument("--param", action="append", default=[])
    trigger_parser.add_argument("--wait", action="store_true")
    trigger_parser.add_argument("--timeout", type=float, default=3600.0)
    trigger_parser.add_argument("--poll-interval", type=float, default=5.0)
    trigger_parser.add_argument("--authorized", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = _client_from_args(args)
        if args.command == "inspect":
            _print(inspect_job(client, args.job))
        elif args.command == "compare":
            _print(compare_jobs(client, args.reference_job, args.target_job))
        elif args.command == "config-get":
            raw = client.get_bytes(job_path(args.job) + "/config.xml")
            write_private_snapshot(args.output, raw)
            _print(
                {
                    "status": "saved",
                    "job": args.job,
                    "output": str(args.output.expanduser().resolve(strict=False)),
                    "config_sha256": sha256_bytes(raw),
                }
            )
        elif args.command == "config-create":
            require_authorized(args.authorized)
            raw = read_config(args.input)
            _print(create_config(client, args.job, raw, args.parent))
        elif args.command == "config-update":
            require_authorized(args.authorized)
            raw = read_config(args.input)
            _print(update_config(client, args.job, raw, args.expected_current_sha256))
        elif args.command == "view-add":
            require_authorized(args.authorized)
            path = view_path(args.view) + "/addJobToView?" + urllib.parse.urlencode(
                {"name": args.job}
            )
            with client.post(path):
                pass
            _print({"status": "added", "view": args.view, "job": args.job})
        elif args.command == "trigger":
            require_authorized(args.authorized)
            params = parse_params(args.param)
            if args.poll_interval <= 0 or args.timeout <= 0:
                raise JenkinsError("timeout and poll interval must be positive")
            _print(
                trigger_build(
                    client,
                    args.job,
                    params,
                    wait=args.wait,
                    timeout=args.timeout,
                    poll_interval=args.poll_interval,
                )
            )
        else:  # pragma: no cover
            raise JenkinsError(f"unsupported command: {args.command}")
        return 0
    except JenkinsError as exc:
        print(json.dumps({"status": "error", "error": redact(str(exc))}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
