#!/usr/bin/env python3 -u
"""Orchestrate a Flutter Web release to S3-compatible object storage.

Single entry-point workflow:
  1. Preflight  – verify git/project state, ensure S3 and web build configurations
  2. Version    – inspect commits, suggest SemVer bump, write pubspec.yaml
  3. Validate   – pub get, code gen, tests, S3 dry-run
  4. Publish    – build Flutter Web, upload immutable/live assets, tag/push
  5. Promote    – promote an existing immutable release to live

Configuration is split across two files under deploy/:

  deploy/s3.env        S3 endpoint, bucket, credentials, cache-control
  deploy/web.env       Flutter Web build options (--wasm, --pwa-strategy, ...)

Both are loaded as env vars.  Only deploy/s3.env is git-ignored (contains
secrets).  deploy/web.env is meant to be committed so the whole team shares
the same build configuration.

On the first run that requires a build, if deploy/web.env is missing the
script will interactively ask for build options and write the file.  Pass
--yes to skip the prompt and use defaults.  Pass --config-build to force
reconfiguration even when the file already exists.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
PREPARE_SCRIPT = SCRIPTS_DIR / "prepare_web_release.py"
FINGERPRINT_SCRIPT = SCRIPTS_DIR / "fingerprint_web_build.py"

VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-[0-9A-Za-z.-]+)?(?P<build>\+[0-9A-Za-z.-]+)?$"
)

ENTRYPOINT_PATTERNS = [
    "index.html",
    "*.html",
    "flutter.js",
    "flutter_bootstrap.js",
    "flutter_service_worker.js",
    "manifest.json",
    "version.json",
]
STATIC_PATTERNS = [
    "assets/fonts/*",
    "canvaskit/*",
    "icons/*",
    "favicon.png",
]

# ---------------------------------------------------------------------------
# Web build defaults (used when neither env var nor deploy/web.env provide a value)
# ---------------------------------------------------------------------------

WEB_BUILD_DEFAULTS: dict[str, str] = {
    "BUILD_WEB_DIR": "build/web",
    "BUILD_WASM": "0",
    "FINGERPRINT_WEB_BUILD": "1",
    "PWA_STRATEGY": "none",
    "BASE_HREF": "/",
    "FLUTTER_WEB_RENDERER": "",
    "FLUTTER_WEB_OPTIMIZATION": "",
    "FLUTTER_WEB_DART2JS_OPTIMIZATION": "",
    "FLUTTER_WEB_CSP": "0",
    "SOURCE_MAPS": "0",
}

WEB_BUILD_KEYS = list(WEB_BUILD_DEFAULTS)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[release-web-s3] {msg}", flush=True)


def fail(msg: str) -> NoReturn:
    print(f"[release-web-s3] ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture: bool = False,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(a) for a in args)
    if dry_run:
        log(f"[dry-run] $ {quoted}")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    log(f"$ {quoted}")
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env or os.environ,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        fail(f"Command failed ({result.returncode}): {quoted}\n{stderr}")
    return result


def run_capture(args: list[str], **kwargs) -> str:
    return run(args, capture=True, **kwargs).stdout.strip()


def step(i: int, title: str) -> None:
    print(f"\n{'─' * 60}\n  Step {i}: {title}\n{'─' * 60}\n", flush=True)


def bool_enabled(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def strip_edge_slashes(value: str) -> str:
    return value.strip("/")


def join_prefix(left: str, right: str) -> str:
    left = strip_edge_slashes(left)
    right = strip_edge_slashes(right)
    if not left:
        return right
    if not right:
        return left
    return f"{left}/{right}"


def s3_uri(bucket: str, prefix: str) -> str:
    prefix = strip_edge_slashes(prefix)
    return f"s3://{bucket}" if not prefix else f"s3://{bucket}/{prefix}"


def dotenv_read(path: Path) -> dict[str, str]:
    """Read a KEY=value .env file into a dict (no interpolation)."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def dotenv_write(path: Path, data: dict[str, str], *, header: str = "") -> None:
    lines: list[str] = []
    if header:
        lines.append(header)
        lines.append("")
    for k, v in data.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Project detection
# ---------------------------------------------------------------------------


def project_uses_fvm(project_root: Path) -> bool:
    return any((project_root / p).exists() for p in (".fvm/fvm_config.json", ".fvmrc", ".fvm"))


def detect_flutter_cmd(project_root: Path) -> list[str]:
    env_value = os.environ.get("FLUTTER_CMD", "").strip()
    if env_value:
        return shlex.split(env_value)
    return ["fvm", "flutter"] if project_uses_fvm(project_root) else ["flutter"]


def detect_dart_cmd(project_root: Path) -> list[str]:
    env_value = os.environ.get("DART_CMD", "").strip()
    if env_value:
        return shlex.split(env_value)
    return ["fvm", "dart"] if project_uses_fvm(project_root) else ["dart"]


def has_slang(project_root: Path) -> bool:
    if (project_root / "slang.yaml").exists():
        return True
    pubspec = project_root / "pubspec.yaml"
    return pubspec.exists() and "slang:" in pubspec.read_text(encoding="utf-8")


def has_build_runner(project_root: Path) -> bool:
    pubspec = project_root / "pubspec.yaml"
    return pubspec.exists() and "build_runner" in pubspec.read_text(encoding="utf-8")


def read_pubspec_value(project_root: Path, key: str) -> str:
    pubspec = project_root / "pubspec.yaml"
    text = pubspec.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(key)}:\s*['\"]?([^'\"#\s]+)['\"]?", text)
    return match.group(1) if match else ""


def detect_project_root(args: argparse.Namespace) -> Path:
    if args.project_root:
        p = Path(args.project_root).resolve()
        if p.exists():
            return p
        fail(f"--project-root does not exist: {p}")
    try:
        return Path(run_capture(["git", "rev-parse", "--show-toplevel"]))
    except SystemExit:
        current = Path.cwd()
        while current != current.parent:
            if (current / "pubspec.yaml").exists():
                return current
            current = current.parent
        fail("Cannot detect Flutter project root. Use --project-root.")


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------


def load_s3_env(project_root: Path) -> dict[str, str]:
    """Merge process env onto deploy/s3.env (file wins for keys it defines)."""
    base = os.environ.copy()
    file_vars = dotenv_read(project_root / "deploy" / "s3.env")
    base.update(file_vars)
    return base


def load_web_env(project_root: Path) -> dict[str, str]:
    """Merge process env → defaults → deploy/web.env (file wins for keys it defines)."""
    base = os.environ.copy()
    for k, v in WEB_BUILD_DEFAULTS.items():
        base.setdefault(k, v)
    file_vars = dotenv_read(project_root / "deploy" / "web.env")
    base.update(file_vars)
    return base


def ensure_gitignore(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    entries = ["deploy/s3.env"]
    to_add = list(entries)
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        to_add = [e for e in entries if e not in content]
        if to_add:
            with gitignore.open("a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(to_add) + "\n")
            log(f"Added to .gitignore: {', '.join(to_add)}")
    else:
        gitignore.write_text("\n".join(entries) + "\n", encoding="utf-8")
        log("Created .gitignore")


# ---------------------------------------------------------------------------
# Interactive configuration helpers
# ---------------------------------------------------------------------------


def _ask(message: str, default: str) -> str:
    value = input(f"  {message} [{default}]: ").strip()
    return value if value else default


def _ask_bool(prompt: str, default: bool) -> str:
    default_str = "yes" if default else "no"
    value = input(f"  {prompt} [{default_str}]: ").strip().lower()
    if value in {"yes", "y", "true", "1"}:
        return "1"
    if value in {"no", "n", "false", "0"}:
        return "0"
    return "1" if default else "0"


def configure_web_build_interactive(project_root: Path, current: dict[str, str]) -> dict[str, str]:
    """Interactively configure web build options.  Returns the new env dict."""
    print()
    log("Configure Flutter Web build options (press Enter to keep current value):")

    result = copy.deepcopy(current)
    result["BASE_HREF"] = _ask("Base href", current.get("BASE_HREF", "/"))
    result["PWA_STRATEGY"] = _ask("PWA strategy (none / offline-first)", current.get("PWA_STRATEGY", "none"))
    result["BUILD_WASM"] = _ask_bool("Enable WebAssembly (--wasm)", bool_enabled(current.get("BUILD_WASM")))
    result["FINGERPRINT_WEB_BUILD"] = _ask_bool(
        "Enable hashed web asset fingerprinting",
        bool_enabled(current.get("FINGERPRINT_WEB_BUILD", "1")),
    )
    renderer = current.get("FLUTTER_WEB_RENDERER", "")
    result["FLUTTER_WEB_RENDERER"] = _ask("Web renderer (canvaskit / skwasm / html / auto)", renderer)
    result["SOURCE_MAPS"] = _ask_bool("Generate source maps", bool_enabled(current.get("SOURCE_MAPS")))

    csp = current.get("FLUTTER_WEB_CSP", "0")
    result["FLUTTER_WEB_CSP"] = _ask_bool("Enable Content Security Policy mode", bool_enabled(csp))

    opt = current.get("FLUTTER_WEB_OPTIMIZATION", "")
    result["FLUTTER_WEB_OPTIMIZATION"] = _ask("Dart optimization level (O0-O4 / leave empty for default)", opt)

    d2js = current.get("FLUTTER_WEB_DART2JS_OPTIMIZATION", "")
    result["FLUTTER_WEB_DART2JS_OPTIMIZATION"] = _ask(
        "dart2js optimization level (O0-O4 / leave empty for default)", d2js
    )

    result["BUILD_WEB_DIR"] = _ask("Build output directory", current.get("BUILD_WEB_DIR", "build/web"))

    # Clean empty values so the written file stays tidy
    cleaned = {k: v for k, v in result.items() if v}
    for k in WEB_BUILD_KEYS:
        cleaned.setdefault(k, "")

    return cleaned


def ensure_web_build_config(ctx: Context) -> None:
    """Load deploy/web.env; if missing and interactive, ask the user."""
    web_file = ctx.project_root / "deploy" / "web.env"
    if web_file.exists() and not ctx.args.config_build:
        log(f"Web build config: {web_file}")

    # Merge process env + defaults + file (file wins)
    file_vars = dotenv_read(web_file) if web_file.exists() else {}
    merged = copy.deepcopy(WEB_BUILD_DEFAULTS)
    for k, v in os.environ.items():
        if k in WEB_BUILD_KEYS:
            merged[k] = v
    merged.update(file_vars)
    merged.setdefault("BUILD_WEB_DIR", "build/web")

    if web_file.exists() and not ctx.args.config_build:
        ctx.web_env = merged
        _print_current_web_config(ctx)
        return

    # No file yet, or user requested --config-build
    if ctx.args.yes:
        log("Non-interactive mode; using default web build options.")
        ctx.web_env = merged
        write_web_env_file(ctx.project_root, merged)
        return

    new_config = configure_web_build_interactive(ctx.project_root, merged)
    write_web_env_file(ctx.project_root, new_config)
    ctx.web_env = new_config


def write_web_env_file(project_root: Path, data: dict[str, str]) -> None:
    deploy_dir = project_root / "deploy"
    deploy_dir.mkdir(parents=True, exist_ok=True)
    # Only persist keys that have non-empty values
    to_write = {k: v for k, v in data.items() if v}
    # Always include the required keys so the file is a complete reference
    for key in WEB_BUILD_KEYS:
        to_write.setdefault(key, "")
    header = (
        "# Flutter Web build configuration — safe to commit.\n"
        "# Run 'release_web_s3.py --config-build' to reconfigure interactively."
    )
    dotenv_write(deploy_dir / "web.env", to_write, header=header)
    log(f"Web build config written: deploy/web.env")


def _print_current_web_config(ctx: Context) -> None:
    lines = [
        f"  Base href:       {ctx.web_env.get('BASE_HREF', '/')}",
        f"  PWA strategy:    {ctx.web_env.get('PWA_STRATEGY', 'none')}",
        f"  WASM:            {'yes' if bool_enabled(ctx.web_env.get('BUILD_WASM')) else 'no'}",
        f"  Fingerprint:     {'yes' if bool_enabled(ctx.web_env.get('FINGERPRINT_WEB_BUILD')) else 'no'}",
        f"  Renderer:        {ctx.web_env.get('FLUTTER_WEB_RENDERER') or 'default'}",
        f"  Source maps:     {'yes' if bool_enabled(ctx.web_env.get('SOURCE_MAPS')) else 'no'}",
        f"  CSP mode:        {'yes' if bool_enabled(ctx.web_env.get('FLUTTER_WEB_CSP')) else 'no'}",
        f"  Build dir:       {ctx.web_env.get('BUILD_WEB_DIR', 'build/web')}",
    ]
    for line in lines:
        log(line)


def configure_s3_interactive(project_root: Path) -> None:
    deploy_dir = project_root / "deploy"
    deploy_dir.mkdir(parents=True, exist_ok=True)

    example = deploy_dir / "s3.env.example"
    if not example.exists():
        example.write_text(
            "S3_ENDPOINT_URL=https://s3.example.com\n"
            "S3_BUCKET=my-bucket\n"
            "S3_REGION=auto\n"
            "S3_LIVE_PREFIX=web\n"
            "S3_RELEASE_PREFIX=web/releases\n"
            "# AWS_PROFILE=my-profile\n",
            encoding="utf-8",
        )
        log(f"Created {example}")

    print()
    print("Configure S3 deployment:")
    endpoint = input("  S3_ENDPOINT_URL: ").strip()
    bucket = input("  S3_BUCKET: ").strip()
    region = _ask("Region", "auto")
    live_prefix = _ask("Live prefix", "web")
    release_prefix = _ask("Release prefix", "web/releases")
    profile = input("  AWS_PROFILE (optional): ").strip()

    lines = [
        f"S3_ENDPOINT_URL={endpoint}",
        f"S3_BUCKET={bucket}",
        f"S3_REGION={region}",
        f"S3_LIVE_PREFIX={live_prefix}",
        f"S3_RELEASE_PREFIX={release_prefix}",
    ]
    if profile:
        lines.append(f"AWS_PROFILE={profile}")

    env_file = deploy_dir / "s3.env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Created deploy/s3.env")


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------


def ensure_s3_required(s3_env: dict[str, str]) -> None:
    for key in ["S3_ENDPOINT_URL", "S3_BUCKET"]:
        if not s3_env.get(key):
            fail(f"Missing required configuration: {key}")
    s3_env.setdefault("S3_REGION", "auto")
    s3_env.setdefault("S3_LIVE_PREFIX", "web")
    s3_env.setdefault("S3_RELEASE_PREFIX", "web/releases")
    s3_env.setdefault("RELEASE_CACHE_CONTROL", "public,max-age=31536000,immutable")
    s3_env.setdefault("LIVE_CACHE_CONTROL", "no-cache, no-store, must-revalidate")
    s3_env.setdefault("LIVE_STATIC_CACHE_CONTROL", s3_env["LIVE_CACHE_CONTROL"])
    s3_env.setdefault("LIVE_HASHED_CACHE_CONTROL", s3_env["RELEASE_CACHE_CONTROL"])


def aws_base_args(s3_env: dict[str, str]) -> list[str]:
    args = ["aws", "--endpoint-url", s3_env["S3_ENDPOINT_URL"], "--region", s3_env.get("S3_REGION", "auto")]
    if s3_env.get("AWS_PROFILE"):
        args += ["--profile", s3_env["AWS_PROFILE"]]
    return args


def verify_s3_connectivity(ctx: Context) -> None:
    if run(["aws", "--version"], capture=True, check=False).returncode != 0:
        log("aws CLI not found — skipping connectivity check.")
        return
    bucket = ctx.s3_env.get("S3_BUCKET", "")
    endpoint = ctx.s3_env.get("S3_ENDPOINT_URL", "")
    if not bucket or not endpoint:
        log("Skipping S3 connectivity check (missing S3 config).")
        return
    log(f"Testing S3 connectivity to {endpoint}/{bucket}...")
    result = run(aws_base_args(ctx.s3_env) + ["s3", "ls", f"s3://{bucket}/"], capture=True, check=False)
    if result.returncode == 0:
        log("S3 connectivity OK.")
        return
    if ctx.args.yes:
        fail(f"S3 connectivity failed:\n{result.stderr}")
    log((result.stderr or result.stdout or "").strip())
    if input("Continue despite S3 connectivity failure? [y/N] ").strip().lower() not in {"y", "yes"}:
        fail("Aborted due to S3 connectivity failure.")


def validate_prefixes(s3_env: dict[str, str]) -> None:
    live = strip_edge_slashes(s3_env.get("S3_LIVE_PREFIX", "web"))
    release = strip_edge_slashes(s3_env.get("S3_RELEASE_PREFIX", "web/releases"))
    if release.startswith(live + "/"):
        log(
            "WARNING: S3_RELEASE_PREFIX is nested under S3_LIVE_PREFIX. "
            "The uploader excludes releases/** during live sync to protect immutable releases."
        )


def aws_sync(
    s3_env: dict[str, str],
    source: str,
    dest: str,
    *,
    cache_control: str,
    excludes: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    args = aws_base_args(s3_env) + ["s3", "sync", source, dest, "--delete", "--cache-control", cache_control]
    for pattern in excludes or []:
        args += ["--exclude", pattern]
    run(args, dry_run=dry_run)


def aws_cp_filtered(
    s3_env: dict[str, str],
    source: str,
    dest: str,
    *,
    includes: list[str],
    cache_control: str,
    source_is_s3: bool,
    dry_run: bool = False,
) -> None:
    args = aws_base_args(s3_env) + ["s3", "cp", source, dest, "--recursive", "--exclude", "*", "--exclude", "releases/**"]
    for pattern in includes:
        args += ["--include", pattern]
    args += ["--cache-control", cache_control]
    if source_is_s3:
        args += ["--metadata-directive", "REPLACE"]
    run(args, dry_run=dry_run)


def aws_cp_exact_paths(
    s3_env: dict[str, str],
    source_root: str | Path,
    dest_root: str,
    *,
    paths: list[str],
    cache_control: str,
    source_is_s3: bool,
    dry_run: bool = False,
) -> None:
    if not paths:
        return
    for rel in paths:
        if source_is_s3:
            source = f"{str(source_root).rstrip('/')}/{rel}"
        else:
            source = str(Path(source_root) / rel)
        dest = f"{dest_root.rstrip('/')}/{rel}"
        args = aws_base_args(s3_env) + ["s3", "cp", source, dest, "--cache-control", cache_control]
        if source_is_s3:
            args += ["--metadata-directive", "REPLACE"]
        run(args, dry_run=dry_run)


def fingerprint_manifest_path(build_dir: Path) -> Path:
    return build_dir.parent / "web_fingerprint_manifest.json"


def fingerprint_web_build(ctx: Context, build_dir: Path) -> dict[str, list[str]] | None:
    if not bool_enabled(ctx.web_env.get("FINGERPRINT_WEB_BUILD")):
        log("Web fingerprinting disabled by FINGERPRINT_WEB_BUILD.")
        return None
    if ctx.args.dry_run:
        log(f"[dry-run] Would fingerprint cacheable web assets in {build_dir}")
        return None
    if not FINGERPRINT_SCRIPT.exists():
        fail(f"Missing fingerprint script: {FINGERPRINT_SCRIPT}")
    manifest_path = fingerprint_manifest_path(build_dir)
    output = run_capture(
        [sys.executable, str(FINGERPRINT_SCRIPT), str(build_dir), "--manifest-out", str(manifest_path)],
        cwd=ctx.project_root,
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        fail(f"Fingerprint script returned invalid JSON: {exc}\n{output}")
    log(
        "Fingerprinting complete: "
        f"{len(payload.get('hashed_files', []))} hashed files, "
        f"{len(payload.get('stable_files', []))} stable files."
    )
    return payload


def publish_to_s3(ctx: Context, *, dry_run: bool, build: bool) -> None:
    build_dir = ctx.project_root / ctx.web_env["BUILD_WEB_DIR"]
    if build:
        build_web(ctx)
    if not build_dir.exists() and not dry_run:
        fail(f"Build output not found: {build_dir}")
    write_version_json(ctx, build_dir)
    fingerprint = fingerprint_web_build(ctx, build_dir)

    bucket = ctx.s3_env["S3_BUCKET"]
    live_uri = s3_uri(bucket, ctx.s3_env["S3_LIVE_PREFIX"])
    release_uri = s3_uri(bucket, join_prefix(ctx.s3_env["S3_RELEASE_PREFIX"], ctx.release_id))

    aws_sync(ctx.s3_env, str(build_dir), release_uri, cache_control=ctx.s3_env["RELEASE_CACHE_CONTROL"], dry_run=dry_run)
    aws_sync(ctx.s3_env, str(build_dir), live_uri, cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"], excludes=["releases/**"], dry_run=dry_run)
    if fingerprint:
        aws_cp_exact_paths(
            ctx.s3_env,
            build_dir,
            live_uri,
            paths=fingerprint["stable_files"],
            cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"],
            source_is_s3=False,
            dry_run=dry_run,
        )
        aws_cp_exact_paths(
            ctx.s3_env,
            build_dir,
            live_uri,
            paths=fingerprint["hashed_files"],
            cache_control=ctx.s3_env["LIVE_HASHED_CACHE_CONTROL"],
            source_is_s3=False,
            dry_run=dry_run,
        )
    else:
        aws_cp_filtered(
            ctx.s3_env,
            str(build_dir),
            live_uri,
            includes=["*"],
            cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"],
            source_is_s3=False,
            dry_run=dry_run,
        )


def promote_release(ctx: Context, release_id: str, *, dry_run: bool) -> None:
    bucket = ctx.s3_env["S3_BUCKET"]
    live_uri = s3_uri(bucket, ctx.s3_env["S3_LIVE_PREFIX"])
    release_uri = s3_uri(bucket, join_prefix(ctx.s3_env["S3_RELEASE_PREFIX"], release_id))
    build_dir = ctx.project_root / ctx.web_env["BUILD_WEB_DIR"]
    manifest_path = fingerprint_manifest_path(build_dir)
    fingerprint = None
    if manifest_path.exists():
        fingerprint = json.loads(manifest_path.read_text(encoding="utf-8"))
    aws_sync(ctx.s3_env, release_uri, live_uri, cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"], dry_run=dry_run)
    if fingerprint:
        aws_cp_exact_paths(
            ctx.s3_env,
            release_uri,
            live_uri,
            paths=fingerprint["stable_files"],
            cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"],
            source_is_s3=True,
            dry_run=dry_run,
        )
        aws_cp_exact_paths(
            ctx.s3_env,
            release_uri,
            live_uri,
            paths=fingerprint["hashed_files"],
            cache_control=ctx.s3_env["LIVE_HASHED_CACHE_CONTROL"],
            source_is_s3=True,
            dry_run=dry_run,
        )
    else:
        aws_cp_filtered(
            ctx.s3_env,
            release_uri,
            live_uri,
            includes=["*"],
            cache_control=ctx.s3_env["LIVE_CACHE_CONTROL"],
            source_is_s3=True,
            dry_run=dry_run,
        )


# ---------------------------------------------------------------------------
# Flutter Web build
# ---------------------------------------------------------------------------


def build_web(ctx: Context) -> None:
    """Run `flutter build web` using web.env settings."""
    pre = ctx.s3_env.get("PRE_BUILD_CMD", "") or ctx.web_env.get("PRE_BUILD_CMD", "")
    if pre:
        # PRE_BUILD_CMD can come from either file; prefer s3_env for back-compat
        run(["bash", "-lc", pre], cwd=ctx.project_root, dry_run=ctx.args.dry_run)

    build_args = ["build", "web"]

    # --base-href
    build_args += ["--base-href", ctx.web_env.get("BASE_HREF", "/")]

    # --pwa-strategy
    pwa = ctx.web_env.get("PWA_STRATEGY", "none")
    build_args += [f"--pwa-strategy={pwa}"]

    # --wasm
    if bool_enabled(ctx.web_env.get("BUILD_WASM")):
        log("WebAssembly: enabled (--wasm)")
        build_args.append("--wasm")

    # --web-renderer
    renderer = ctx.web_env.get("FLUTTER_WEB_RENDERER", "").strip()
    if renderer and renderer != "auto":
        build_args += ["--web-renderer", renderer]

    # --source-maps
    if bool_enabled(ctx.web_env.get("SOURCE_MAPS")):
        build_args.append("--source-maps")

    # --csp
    if bool_enabled(ctx.web_env.get("FLUTTER_WEB_CSP")):
        build_args.append("--csp")

    # --dart2js-optimization
    d2js = ctx.web_env.get("FLUTTER_WEB_DART2JS_OPTIMIZATION", "").strip()
    if d2js and d2js != "O0":
        # O0 is default so skip it
        build_args += ["--dart2js-optimization", d2js]

    # --optimization-level (Flutter 3.29+)
    opt = ctx.web_env.get("FLUTTER_WEB_OPTIMIZATION", "").strip()
    if opt:
        build_args += ["--optimization-level", opt]

    # --release is implied by `flutter build web` but make it explicit
    if "--release" not in build_args:
        build_args.append("--release")

    log(f"Build args: {' '.join(build_args)}")
    run(ctx.flutter_cmd + build_args, cwd=ctx.project_root, dry_run=ctx.args.dry_run)


def write_version_json(ctx: Context, build_dir: Path) -> None:
    pubspec_name = read_pubspec_value(ctx.project_root, "name")
    pubspec_version = read_pubspec_value(ctx.project_root, "version")
    if not pubspec_name or not pubspec_version:
        fail("Unable to read pubspec name/version.")
    app_version = pubspec_version.split("+", 1)[0]
    build_number = pubspec_version.split("+", 1)[1] if "+" in pubspec_version else ""
    payload = {
        "app_name": pubspec_name,
        "version": app_version,
        "package_name": pubspec_name,
        "build_number": build_number,
        "releaseId": ctx.release_id,
        "gitSha": run_capture(["git", "rev-parse", "HEAD"], cwd=ctx.project_root),
        "builtAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseHref": ctx.web_env.get("BASE_HREF", "/"),
        "s3Bucket": ctx.s3_env["S3_BUCKET"],
        "s3LivePrefix": ctx.s3_env["S3_LIVE_PREFIX"],
        "s3ReleasePrefix": ctx.s3_env["S3_RELEASE_PREFIX"],
    }
    if ctx.args.dry_run:
        log(f"[dry-run] Would write {build_dir / 'version.json'}")
        return
    (build_dir / "version.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------


def check_git_behind() -> int:
    out = run_capture(["git", "rev-list", "--count", "HEAD..@{upstream}"], check=False)
    try:
        return int(out) if out else 0
    except ValueError:
        return 0


def step_preflight(ctx: Context) -> None:
    step(1, "Preflight")
    log(f"Project root: {ctx.project_root}")
    log(f"Git branch: {run_capture(['git', 'branch', '--show-current'])}")

    # Git status
    status = run_capture(["git", "status", "--short"])
    if status:
        print(status)
        if not ctx.args.yes and input("Uncommitted changes detected. Continue anyway? [y/N] ").strip().lower() not in {"y", "yes"}:
            fail("Aborted: uncommitted changes.")
    else:
        log("Working tree is clean.")

    # Upstream
    behind = check_git_behind()
    if behind > 0:
        log(f"Branch is {behind} commit(s) behind upstream.")
        if not ctx.args.yes and input("Pull before releasing? [Y/n] ").strip().lower() in {"", "y", "yes"}:
            run(["git", "pull"], cwd=ctx.project_root)

    # Project shape
    missing = [p for p in ["pubspec.yaml", "lib", "web"] if not (ctx.project_root / p).exists()]
    if missing:
        fail(f"Not a Flutter Web project; missing: {', '.join(missing)}")

    # Commands
    ctx.flutter_cmd = detect_flutter_cmd(ctx.project_root)
    ctx.dart_cmd = detect_dart_cmd(ctx.project_root)
    ctx.has_slang = has_slang(ctx.project_root)
    ctx.has_build_runner = has_build_runner(ctx.project_root)
    log(f"Flutter: {' '.join(ctx.flutter_cmd)}")
    log(f"Dart: {' '.join(ctx.dart_cmd)}")

    # deploy/ directory
    (ctx.project_root / "deploy").mkdir(parents=True, exist_ok=True)
    ensure_gitignore(ctx.project_root)

    # --- S3 configuration ---
    s3_file = ctx.project_root / "deploy" / "s3.env"
    if not s3_file.exists() and not os.environ.get("S3_ENDPOINT_URL"):
        if ctx.args.yes:
            fail("Missing deploy/s3.env and S3_ENDPOINT_URL is not set.")
        if input("Create deploy/s3.env interactively? [Y/n] ").strip().lower() in {"", "y", "yes"}:
            configure_s3_interactive(ctx.project_root)
        else:
            fail("S3 configuration is required.")

    ctx.s3_env = load_s3_env(ctx.project_root)
    ensure_s3_required(ctx.s3_env)
    validate_prefixes(ctx.s3_env)
    verify_s3_connectivity(ctx)

    # --- Web build configuration ---
    ensure_web_build_config(ctx)
    # Carry over PRE_BUILD_CMD / BUILD_RUNNER_CMD / SLANG_CMD / TEST_CMD
    # from s3_env (legacy) so they're available in validate/publish steps
    for legacy_key in ("PRE_BUILD_CMD", "BUILD_RUNNER_CMD", "SLANG_CMD", "TEST_CMD"):
        val = ctx.s3_env.get(legacy_key, "")
        if val:
            ctx.web_env.setdefault(legacy_key, val)


def step_version(ctx: Context) -> None:
    step(2, "Version")
    prep_args = [
        sys.executable,
        str(PREPARE_SCRIPT),
        "--pubspec",
        str(ctx.project_root / ctx.args.pubspec),
        "--tag-match",
        ctx.args.tag_match,
        "--tag-prefix",
        ctx.args.tag_prefix,
        "--json",
    ]
    report = json.loads(run_capture(prep_args, cwd=ctx.project_root))
    print(f"  Current version: {report['current_version']}")
    print(f"  Last tag:        {report['last_tag'] or 'None'}")
    print(f"  Commits since:   {report['commit_count']}")
    print(f"  Detected bump:   {report['detected_bump']}")
    print(f"  Suggested:       {report['suggested_version']}  →  {report['tag_name']}")

    version = ctx.args.version or report["suggested_version"] or report["current_version"]
    if ctx.args.bump:
        bump_report = json.loads(
            run_capture(
                [
                    sys.executable,
                    str(PREPARE_SCRIPT),
                    "--pubspec",
                    str(ctx.project_root / ctx.args.pubspec),
                    "--bump",
                    ctx.args.bump,
                    "--json",
                ],
                cwd=ctx.project_root,
            )
        )
        version = bump_report["version"]

    if not ctx.args.yes:
        user_value = input(f"Release version [{version}]: ").strip()
        if user_value:
            version = user_value
    if not VERSION_RE.match(version):
        fail(f"Invalid version: {version}")

    ctx.version = version
    ctx.tag_name = f"{ctx.args.tag_prefix}{version}"
    ctx.release_id = version

    if ctx.args.dry_run:
        log(f"[dry-run] Would update pubspec.yaml to {version}")
    else:
        run(
            [
                sys.executable,
                str(PREPARE_SCRIPT),
                "--pubspec",
                str(ctx.project_root / ctx.args.pubspec),
                "--version",
                version,
                "--tag-prefix",
                ctx.args.tag_prefix,
                "--write",
            ],
            cwd=ctx.project_root,
        )
        log(f"Updated pubspec.yaml to version {version}")


def step_validate(ctx: Context) -> None:
    step(3, "Validate")
    run(ctx.flutter_cmd + ["pub", "get"], cwd=ctx.project_root, dry_run=ctx.args.dry_run)

    # Codegen — prefer explicit override, then auto-detect
    build_runner_cmd = ctx.web_env.get("BUILD_RUNNER_CMD", "")
    if build_runner_cmd:
        run(["bash", "-lc", build_runner_cmd], cwd=ctx.project_root, dry_run=ctx.args.dry_run)
    elif ctx.has_build_runner:
        run(ctx.dart_cmd + ["run", "build_runner", "build", "-d"], cwd=ctx.project_root, dry_run=ctx.args.dry_run)

    slang_cmd = ctx.web_env.get("SLANG_CMD", "")
    if slang_cmd:
        run(["bash", "-lc", slang_cmd], cwd=ctx.project_root, dry_run=ctx.args.dry_run)
    elif ctx.has_slang:
        run(ctx.dart_cmd + ["run", "slang"], cwd=ctx.project_root, dry_run=ctx.args.dry_run)

    # Tests
    if ctx.args.skip_tests:
        log("Skipping tests (--skip-tests).")
    else:
        test_cmd = ctx.web_env.get("TEST_CMD", "")
        result = (
            run(["bash", "-lc", test_cmd], cwd=ctx.project_root, check=False, dry_run=ctx.args.dry_run)
            if test_cmd
            else run(ctx.flutter_cmd + ["test"], cwd=ctx.project_root, check=False, dry_run=ctx.args.dry_run)
        )
        if result.returncode != 0 and not ctx.args.dry_run:
            if ctx.args.yes:
                fail("Tests failed.")
            if input("Tests failed. Continue anyway? [y/N] ").strip().lower() not in {"y", "yes"}:
                fail("Aborted: tests failed.")

    log("S3 upload dry-run...")
    publish_to_s3(ctx, dry_run=True, build=False)


def step_publish(ctx: Context) -> None:
    step(4, "Publish")
    publish_to_s3(ctx, dry_run=ctx.args.dry_run, build=True)
    if not ctx.args.dry_run and not ctx.args.no_tag:
        run(["git", "tag", ctx.tag_name], cwd=ctx.project_root)
        if not ctx.args.no_push:
            run(["git", "push", "origin", ctx.tag_name], cwd=ctx.project_root)
    log("Publish complete.")


def step_promote(ctx: Context) -> None:
    step(3, "Promote")
    promote_release(ctx, ctx.args.promote, dry_run=ctx.args.dry_run)
    log(f"Promotion complete: {ctx.args.promote}")


# ---------------------------------------------------------------------------
# Context & arg parsing
# ---------------------------------------------------------------------------


@dataclass
class Context:
    args: argparse.Namespace
    project_root: Path
    s3_env: dict[str, str] = field(default_factory=dict)
    web_env: dict[str, str] = field(default_factory=dict)
    flutter_cmd: list[str] = field(default_factory=list)
    dart_cmd: list[str] = field(default_factory=list)
    has_slang: bool = False
    has_build_runner: bool = False
    version: str = ""
    tag_name: str = ""
    release_id: str = ""


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Release Flutter Web to S3-compatible object storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Configuration files:\n"
            "  deploy/s3.env   S3 endpoint, bucket, credentials (git-ignored)\n"
            "  deploy/web.env  Flutter Web build options (safe to commit)\n"
        ),
    )
    p.add_argument("--project-root", help="Flutter project root; default auto-detect via git or pubspec.yaml")
    p.add_argument("--pubspec", default="pubspec.yaml", help="Path to pubspec.yaml relative to project root")
    p.add_argument("--tag-match", default="web-v*", help="Git tag glob used to find the previous web release")
    p.add_argument("--tag-prefix", default="web-v", help="Git tag prefix for the new release")
    p.add_argument("--version", help="Explicit release version; overrides auto-suggested version")
    p.add_argument("--bump", choices=["major", "minor", "patch"], help="Override SemVer bump type")
    p.add_argument("--dry-run", action="store_true", help="Print planned actions without modifying files or S3")
    p.add_argument("--skip-tests", action="store_true", help="Skip the test step during validation")
    p.add_argument("--no-tag", action="store_true", help="Do not create the release git tag")
    p.add_argument("--no-push", action="store_true", help="Do not push the release git tag")
    p.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode; fail instead of prompting")
    p.add_argument(
        "--promote",
        metavar="RELEASE_ID",
        help="Promote an existing immutable release to the live prefix",
    )
    p.add_argument(
        "--config-build",
        action="store_true",
        help="Force interactive reconfiguration of web build options (deploy/web.env)",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ctx = Context(args=args, project_root=detect_project_root(args))

    if args.dry_run:
        log("DRY RUN MODE")
    if args.yes:
        log("Non-interactive mode")

    step_preflight(ctx)

    if args.promote:
        step_promote(ctx)
        return 0

    step_version(ctx)
    step_validate(ctx)
    step_publish(ctx)
    print(f"\n{'=' * 60}\n  Release complete: {ctx.version} ({ctx.tag_name})\n{'=' * 60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
