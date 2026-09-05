#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "markdown-it-py>=4,<5",
#   "PyYAML>=6,<7",
#   "regex>=2024.11.6",
# ]
# ///
"""Local semantic candidate retrieval for mdq-governed Markdown records."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
import ipaddress
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml


CLI_SCHEMA = "mdq.semantic.cli.v1"
CONFIG_SCHEMA = "mdq.semantic.config.v1"
INDEX_SCHEMA = "mdq.semantic.index.v1"
INDEX_VERSION = 1
DEFAULT_GLOB = "**/*.md"
DEFAULT_CHUNK_CHARS = 1800
DEFAULT_CHUNK_OVERLAP = 250
DEFAULT_TOP_K = 10
MAX_TOP_K = 100
HTTP_TIMEOUT_SECONDS = 30
IGNORED_DIRECTORIES = {
    ".git",
    ".mdq",
    ".next",
    ".nuxt",
    ".output",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

SCRIPT_PATH = Path(__file__).resolve()
SKILLS_ROOT = SCRIPT_PATH.parents[2]
MDQ_SCRIPT = SCRIPT_PATH.with_name("mdq.py")
GLOBAL_CONFIG_PATH = Path.home() / ".config" / "mdq" / "semantic.yaml"


class SemanticError(RuntimeError):
    """A user-actionable semantic CLI failure."""


@dataclass(frozen=True)
class SemanticConfig:
    path: Path
    backend: str
    model: str
    base_url: str
    api_key_env: str | None
    index_relative: str

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
        }


@dataclass(frozen=True)
class IndexedRecord:
    source_path: str
    source_sha256: str
    profile_hash: str
    profile_source: str
    record_key: str
    fields: dict[str, Any]
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    chunk_index: int
    chunk_count: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class VerifiedRecord:
    record: dict[str, Any]
    source_sha256: str
    profile_hash: str
    profile_source: str


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def compact_status(payload: dict[str, Any]) -> None:
    status = payload.get("status", "unknown")
    parts = [str(status)]
    if "count" in payload:
        parts.append(f"count={payload['count']}")
    if "indexed_chunks" in payload:
        parts.append(f"chunks={payload['indexed_chunks']}")
    if "stale_sources" in payload:
        parts.append(f"stale={payload['stale_sources']}")
    sys.stdout.write(" ".join(parts) + "\n")
    for item in payload.get("records", []):
        key = item.get("key") or "<candidate>"
        similarity = item.get("similarity")
        score = f" similarity={similarity:.4f}" if isinstance(similarity, float) else ""
        location = f"{item.get('document')}:{item.get('line_start')}"
        sys.stdout.write(f"record {key}{score} {location}\n")
        if item.get("title") is not None:
            sys.stdout.write(f"title: {item['title']}\n")
        if item.get("snippet"):
            sys.stdout.write(f"snippet: {item['snippet'].replace(chr(10), ' ')}\n")
    diagnostics = payload.get("diagnostics", [])
    for item in diagnostics:
        sys.stdout.write(
            f"{item.get('severity', 'info')}:{item.get('code', 'unknown')}"
            f" {item.get('message', '')}\n"
        )


def finish(payload: dict[str, Any], output: str, returncode: int = 0) -> int:
    if output == "compact":
        compact_status(payload)
    else:
        emit(payload)
    return returncode


def diagnostic(code: str, severity: str, message: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if details:
        result["details"] = details
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def detect_project_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise SemanticError(f"project root is not a directory: {root}")
        return root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd().resolve()


def project_config_path(project_root: Path) -> Path:
    return project_root / ".mdq" / "semantic" / "config.yaml"


def path_has_symlink(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        root = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SemanticError(f"could not load semantic config {path}: {exc}") from exc
    if not isinstance(root, dict):
        raise SemanticError(f"semantic config must be a mapping: {path}")
    return root


def endpoint_host_is_loopback(value: str) -> bool:
    parsed = urlsplit(value)
    host = parsed.hostname
    if host is None:
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_endpoint(value: str, *, trusted_global: bool) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SemanticError("semantic base_url must be an HTTP(S) URL with a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise SemanticError("semantic base_url must not contain URL userinfo")
    if parsed.query or parsed.fragment:
        raise SemanticError("semantic base_url must not contain query or fragment data")
    if not trusted_global and not endpoint_host_is_loopback(value):
        raise SemanticError(
            "project-local semantic config may target only a loopback endpoint; "
            "configure a remote API in the trusted global config"
        )
    return value.rstrip("/")


def resolve_config(project_root: Path, *, required: bool = True) -> SemanticConfig | None:
    candidates = [project_config_path(project_root), GLOBAL_CONFIG_PATH]
    path = next(
        (candidate for candidate in candidates if candidate.is_file() or candidate.is_symlink()),
        None,
    )
    if path is None:
        if required:
            raise SemanticError(
                "semantic backend is not configured; run "
                "mdq-semantic configure --project-root <project>"
            )
        return None
    if path_has_symlink(path):
        raise SemanticError(f"semantic config path must not contain symlinks: {path}")
    root = load_yaml_mapping(path)
    if root.get("schema") != CONFIG_SCHEMA:
        raise SemanticError(
            f"unsupported semantic config schema in {path}; expected {CONFIG_SCHEMA}"
        )
    backend = root.get("backend")
    model = root.get("model")
    base_url = root.get("base_url")
    api_key_env = root.get("api_key_env")
    index_relative = root.get("index", ".mdq/semantic/index.sqlite3")
    if backend not in {"omlx", "ollama", "api"}:
        raise SemanticError("semantic config backend must be omlx, ollama, or api")
    if not isinstance(model, str) or not model.strip():
        raise SemanticError("semantic config model must be non-empty")
    if not isinstance(base_url, str) or not base_url.strip():
        raise SemanticError("semantic config base_url must be non-empty")
    trusted_global = path.resolve() == GLOBAL_CONFIG_PATH.resolve()
    if api_key_env is not None and (
        not isinstance(api_key_env, str)
        or not api_key_env.strip()
        or not api_key_env.isidentifier()
    ):
        raise SemanticError("semantic config api_key_env must be a valid environment variable name")
    if backend != "api" and api_key_env is not None:
        raise SemanticError("api_key_env is allowed only for the api backend")
    if backend == "api" and not trusted_global:
        raise SemanticError(
            "the api backend must be configured in the trusted global config "
            f"{GLOBAL_CONFIG_PATH}"
        )
    base_url = validate_endpoint(base_url, trusted_global=trusted_global)
    if not isinstance(index_relative, str) or not index_relative.strip():
        raise SemanticError("semantic config index must be a non-empty relative path")
    index_path = Path(index_relative)
    if index_path.is_absolute() or ".." in index_path.parts:
        raise SemanticError("semantic config index must stay inside the project root")
    return SemanticConfig(
        path=path,
        backend=backend,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        index_relative=index_relative,
    )


def write_config(
    project_root: Path,
    *,
    backend: str,
    model: str,
    base_url: str,
    api_key_env: str | None,
    index_relative: str,
    global_config: bool,
) -> Path:
    if backend not in {"omlx", "ollama", "api"}:
        raise SemanticError("backend must be omlx, ollama, or api")
    if not model.strip():
        raise SemanticError("model must be non-empty")
    path = GLOBAL_CONFIG_PATH if global_config else project_config_path(project_root)
    if path_has_symlink(path):
        raise SemanticError(f"semantic config path must not contain symlinks: {path}")
    trusted_global = path == GLOBAL_CONFIG_PATH
    if backend == "api" and not trusted_global:
        raise SemanticError(
            "the api backend must be configured globally with --global"
        )
    if backend != "api" and api_key_env is not None:
        raise SemanticError("api_key_env is allowed only for the api backend")
    if api_key_env is not None and not api_key_env.isidentifier():
        raise SemanticError("api_key_env must be a valid environment variable name")
    base_url = validate_endpoint(base_url, trusted_global=trusted_global)
    index = Path(index_relative)
    if index.is_absolute() or ".." in index.parts:
        raise SemanticError("index must stay inside the project root")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": CONFIG_SCHEMA,
        "backend": backend,
        "model": model.strip(),
        "base_url": base_url.rstrip("/"),
        "api_key_env": api_key_env.strip() if api_key_env else None,
        "index": index_relative,
    }
    content = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        if path_has_symlink(path):
            raise SemanticError(f"semantic config path must not contain symlinks: {path}")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return path


def prompt_value(label: str, default: str | None = None, *, required: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    if not value and default is not None:
        value = default
    if required and not value:
        raise SemanticError(f"{label} must be non-empty")
    return value


def configure(args: argparse.Namespace) -> int:
    project_root = detect_project_root(args.project_root)
    backend = args.backend or prompt_value("backend (omlx/ollama/api)")
    if backend not in {"omlx", "ollama", "api"}:
        raise SemanticError("backend must be omlx, ollama, or api")
    default_model = "nomic-embed-text" if backend == "ollama" else None
    model = args.model or prompt_value("embedding model", default_model)
    if args.base_url:
        base_url = args.base_url
    elif backend == "ollama":
        base_url = "http://127.0.0.1:11434"
    elif backend == "omlx":
        base_url = "http://127.0.0.1:8000/v1"
    else:
        base_url = prompt_value("OpenAI-compatible embeddings base URL")
    api_key_env = args.api_key_env
    if backend == "api" and api_key_env is None:
        api_key_env = prompt_value("API key environment variable", "OPENAI_API_KEY")
    path = write_config(
        project_root,
        backend=backend,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        index_relative=args.index,
        global_config=args.global_config,
    )
    return finish(
        {
            "schema": CLI_SCHEMA,
            "status": "configured",
            "project_root": str(project_root),
            "config": str(path),
            "backend": backend,
            "model": model,
            "base_url": base_url,
            "api_key_env": api_key_env,
            "index": args.index,
            "diagnostics": [],
        },
        args.output,
    )


def load_mdq_module() -> Any:
    spec = importlib.util.spec_from_file_location("mdq_semantic_engine", MDQ_SCRIPT)
    if spec is None or spec.loader is None:
        raise SemanticError(f"could not load mdq engine: {MDQ_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_user_path(project_root: Path, raw: str) -> Path:
    value = Path(raw).expanduser()
    value = value if value.is_absolute() else project_root / value
    return Path(os.path.abspath(value))


def normalize_targets(
    project_root: Path,
    raw_targets: list[str],
    patterns: list[str] | None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    targets = [resolve_user_path(project_root, item) for item in raw_targets] or [project_root]
    patterns = patterns or [DEFAULT_GLOB]
    files: dict[Path, None] = {}
    diagnostics: list[dict[str, Any]] = []
    for path in targets:
        if path_has_symlink(path):
            diagnostics.append(
                diagnostic(
                    "semantic_path_unsafe",
                    "error",
                    f"semantic target path must not contain symlinks: {path}",
                )
            )
            continue
        path = path.resolve()
        try:
            path.relative_to(project_root.resolve())
        except ValueError:
            diagnostics.append(
                diagnostic(
                    "semantic_path_outside_project",
                    "error",
                    f"semantic target must stay inside the project root: {path}",
                )
            )
            continue
        if path.is_file():
            if path.suffix.casefold() != ".md":
                diagnostics.append(
                    diagnostic(
                        "semantic_path_invalid",
                        "error",
                        f"semantic target must use the .md extension: {path}",
                    )
                )
            else:
                files[path] = None
            continue
        if not path.is_dir():
            diagnostics.append(
                diagnostic(
                    "semantic_path_invalid",
                    "error",
                    f"semantic target is not a Markdown file or directory: {path}",
                )
            )
            continue
        for pattern in patterns:
            pattern_path = Path(pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts:
                diagnostics.append(
                    diagnostic(
                        "semantic_glob_unsafe",
                        "error",
                        f"semantic glob must stay inside its target directory: {pattern}",
                    )
                )
                continue
            try:
                matches = path.glob(pattern)
            except (OSError, ValueError) as exc:
                diagnostics.append(
                    diagnostic(
                        "semantic_glob_invalid",
                        "error",
                        f"semantic glob {pattern!r} is invalid: {exc}",
                    )
                )
                continue
            for candidate in matches:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                if candidate.suffix.casefold() != ".md":
                    continue
                if any(part in IGNORED_DIRECTORIES for part in candidate.relative_to(path).parts):
                    continue
                files[candidate.resolve()] = None
    return sorted(files), diagnostics


def relative_to_project(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.name


def run_mdq_scan(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return {
            "status": "not_found",
            "count": 0,
            "records": [],
            "documents": [],
            "diagnostics": [],
        }
    command = [
        sys.executable,
        str(MDQ_SCRIPT),
        "scan",
        *(str(path) for path in paths),
        "--require-contract",
        "--limit",
        "1000000",
        "--output",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=SKILLS_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SemanticError(f"could not run mdq structural scan: {exc}") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SemanticError(f"mdq structural scan returned invalid JSON: {detail}") from exc
    if completed.returncode not in {0, 3}:
        return payload
    return payload


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if max_chars < 1 or overlap < 0 or overlap >= max_chars:
        raise SemanticError("chunk size must be positive and overlap must be smaller")
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def request_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise SemanticError(f"semantic backend HTTP {exc.code}") from exc
    except (URLError, HTTPException, TimeoutError, OSError) as exc:
        raise SemanticError(f"semantic backend request failed: {exc}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SemanticError("semantic backend returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise SemanticError("semantic backend response must be a JSON object")
    return result


def normalize_embedding(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise SemanticError("semantic backend returned an empty embedding")
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise SemanticError("semantic backend returned a non-numeric embedding") from exc
    if not all(math.isfinite(item) for item in result):
        raise SemanticError("semantic backend returned a non-finite embedding")
    return result


def embedding_backend(config: SemanticConfig):
    if config.backend == "ollama":
        endpoint = config.base_url
        if not endpoint.endswith("/api/embed"):
            endpoint += "/api/embed"

        def embed(texts: list[str]) -> list[list[float]]:
            response = request_json(endpoint, {"model": config.model, "input": texts})
            values = response.get("embeddings")
            if not isinstance(values, list) or len(values) != len(texts):
                raise SemanticError("Ollama response returned the wrong embedding count")
            return [normalize_embedding(item) for item in values]

        return embed

    endpoint = config.base_url
    if endpoint.endswith("/embeddings"):
        pass
    elif endpoint.endswith("/v1"):
        endpoint += "/embeddings"
    else:
        endpoint += "/v1/embeddings"
    headers: dict[str, str] = {}
    if config.api_key_env:
        token = os.environ.get(config.api_key_env)
        if not token:
            raise SemanticError(
                f"semantic API key environment variable is not set: {config.api_key_env}"
            )
        headers["Authorization"] = f"Bearer {token}"

    def embed(texts: list[str]) -> list[list[float]]:
        response = request_json(
            endpoint,
            {"model": config.model, "input": texts},
            headers=headers,
        )
        values = response.get("data")
        if not isinstance(values, list) or not values:
            raise SemanticError("OpenAI-compatible response does not contain data")
        if any(
            not isinstance(item, dict) or type(item.get("index")) is not int
            for item in values
        ):
            raise SemanticError("OpenAI-compatible response has invalid embedding indices")
        indices = [item["index"] for item in values]
        if sorted(indices) != list(range(len(texts))):
            raise SemanticError("OpenAI-compatible response has non-contiguous embedding indices")
        ordered = sorted(values, key=lambda item: item["index"])
        result = [
            normalize_embedding(item.get("embedding"))
            for item in ordered
            if isinstance(item, dict)
        ]
        if len(result) != len(texts):
            raise SemanticError("semantic backend returned the wrong embedding count")
        return result

    return embed


def embed_batches(
    embed: Any, texts: list[str], batch_size: int
) -> list[list[float]]:
    if batch_size < 1:
        raise SemanticError("embedding batch size must be positive")
    result: list[list[float]] = []
    dimension: int | None = None
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        values = embed(batch)
        if len(values) != len(batch):
            raise SemanticError("semantic backend returned the wrong embedding count")
        for value in values:
            if dimension is None:
                dimension = len(value)
            elif len(value) != dimension:
                raise SemanticError("semantic backend returned inconsistent embedding dimensions")
        result.extend(values)
    return result


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise SemanticError("embedding dimensions differ; rebuild the semantic index")
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def index_path(project_root: Path, config: SemanticConfig) -> Path:
    unresolved = project_root / config.index_relative
    if path_has_symlink(unresolved):
        raise SemanticError(f"semantic index path must not contain symlinks: {unresolved}")
    path = unresolved.resolve()
    try:
        path.relative_to(project_root.resolve())
    except ValueError as exc:
        raise SemanticError("semantic index escapes the project root") from exc
    return path


def ensure_private_file(path: Path) -> None:
    if path_has_symlink(path):
        raise SemanticError(f"semantic cache path must not contain symlinks: {path}")
    if path.exists():
        if not path.is_file():
            raise SemanticError(f"semantic cache path is not a file: {path}")
        os.chmod(path, 0o600)
        return
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        ensure_private_file(path)
    else:
        os.close(descriptor)


def open_database(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(path)
    except sqlite3.DatabaseError as exc:
        raise SemanticError(f"semantic index is not a valid SQLite database: {path}") from exc


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS sources (
            source_path TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_source TEXT NOT NULL,
            indexed_at REAL NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_source TEXT NOT NULL,
            record_key TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            byte_start INTEGER NOT NULL,
            byte_end INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            text TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            UNIQUE(source_path, record_key, chunk_index)
        )"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS chunks_source_idx ON chunks(source_path)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS chunks_key_idx ON chunks(record_key)"
    )


def set_metadata(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    for key, value in values.items():
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )


def get_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    result: dict[str, Any] = {}
    for key, value in rows:
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def source_details(mdq: Any, path: Path) -> tuple[str, str, str]:
    document = mdq.read_document(path)
    if document.profile is None:
        raise SemanticError(f"document has no valid mdq profile: {path}")
    errors = [item for item in document.diagnostics if item.get("severity") == "error"]
    if errors:
        raise SemanticError(f"document mdq profile is invalid: {path}")
    if document.profile_hash is None or document.profile_source is None:
        raise SemanticError(f"document mdq profile could not be identified: {path}")
    return document.source_hash, document.profile_hash, document.profile_source


def records_for_index(
    mdq: Any,
    scan: dict[str, Any],
    project_root: Path,
) -> list[tuple[Path, dict[str, Any], str, str, str]]:
    document_meta = {
        str(Path(item["document"]).resolve()): item
        for item in scan.get("documents", [])
        if isinstance(item, dict) and item.get("document")
    }
    result: list[tuple[Path, dict[str, Any], str, str, str]] = []
    identities: set[tuple[Path, str]] = set()
    for item in scan.get("records", []):
        if not isinstance(item, dict) or not item.get("key"):
            continue
        path = Path(str(item["document"])).resolve()
        identity = (path, str(item["key"]))
        if identity in identities:
            raise SemanticError(
                f"duplicate mdq record identity cannot be semantically indexed: {path}#{item['key']}"
            )
        identities.add(identity)
        meta = document_meta.get(str(path), {})
        source_sha, profile_hash, profile_source = source_details(mdq, path)
        if meta.get("status") == "invalid":
            continue
        result.append((path, item, source_sha, profile_hash, profile_source))
    return result


def command_index(args: argparse.Namespace) -> int:
    project_root = detect_project_root(args.project_root)
    config = resolve_config(project_root)
    assert config is not None
    index = index_path(project_root, config)
    scope_targets = [
        resolve_user_path(project_root, item) for item in args.path
    ] or [project_root]
    scope_patterns = args.glob or [DEFAULT_GLOB]
    paths, path_diagnostics = normalize_targets(project_root, args.path, args.glob)
    if any(item["severity"] == "error" for item in path_diagnostics):
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "invalid",
                "project_root": str(project_root),
                "diagnostics": path_diagnostics,
            },
            args.output,
            3,
        )
    scan = run_mdq_scan(paths)
    scan_errors = [
        item for item in scan.get("diagnostics", []) if item.get("severity") == "error"
    ]
    if scan_errors:
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "invalid",
                "project_root": str(project_root),
                "index": str(index),
                "diagnostics": path_diagnostics + scan_errors,
            },
            args.output,
            3,
        )
    mdq = load_mdq_module()
    try:
        records = records_for_index(mdq, scan, project_root)
        embed = embedding_backend(config)
    except SemanticError:
        raise
    source_groups: dict[Path, list[tuple[dict[str, Any], str, str, str]]] = {}
    for path, record, source_sha, profile_hash, profile_source in records:
        source_groups.setdefault(path, []).append(
            (record, source_sha, profile_hash, profile_source)
        )

    # Embed before opening the SQLite write transaction. A slow or unavailable
    # backend must not hold a cache write lock while the network is in flight.
    prepared_groups: list[
        tuple[
            Path,
            str,
            str,
            str,
            list[tuple[dict[str, Any], str, int, int, list[float]]],
        ]
    ] = []
    for path, grouped in source_groups.items():
        source_sha = grouped[0][1]
        profile_hash = grouped[0][2]
        profile_source = grouped[0][3]
        all_chunks: list[tuple[dict[str, Any], str]] = []
        for record, _, _, _ in grouped:
            raw = path.read_bytes()[
                int(record["byte_start"]) : int(record["byte_end"])
            ].decode("utf-8")
            all_chunks.extend(
                (record, chunk)
                for chunk in chunk_text(raw, args.chunk_chars, args.chunk_overlap)
            )
        if not all_chunks:
            prepared_groups.append(
                (path, source_sha, profile_hash, profile_source, [])
            )
            continue
        embeddings = embed_batches(
            embed,
            [chunk for _, chunk in all_chunks],
            args.batch_size,
        )
        counts: dict[str, int] = {}
        for record, _ in all_chunks:
            key = str(record["key"])
            counts[key] = counts.get(key, 0) + 1
        positions: dict[str, int] = {}
        prepared_chunks: list[tuple[dict[str, Any], str, int, int, list[float]]] = []
        for (record, text), vector in zip(all_chunks, embeddings):
            key = str(record["key"])
            position = positions.get(key, 0)
            positions[key] = position + 1
            prepared_chunks.append((record, text, position, counts[key], vector))
        prepared_groups.append(
            (path, source_sha, profile_hash, profile_source, prepared_chunks)
        )

    index.parent.mkdir(parents=True, exist_ok=True)
    ensure_private_file(index)
    connection = open_database(index)
    try:
        initialize_database(connection)
        previous = get_metadata(connection)
        config_identity = config.identity
        reset = bool(
            previous
            and (
                previous.get("index_schema") != INDEX_SCHEMA
                or previous.get("index_version") != INDEX_VERSION
                or previous.get("config_identity") != config_identity
                or previous.get("project_root") != str(project_root)
            )
        )
        connection.execute("BEGIN")
        try:
            if reset or args.rebuild:
                connection.execute("DELETE FROM chunks")
                connection.execute("DELETE FROM sources")
            else:
                for stale_source in relevant_source_paths(
                    connection, scope_targets, scope_patterns
                ):
                    connection.execute(
                        "DELETE FROM chunks WHERE source_path = ?", (stale_source,)
                    )
                    connection.execute(
                        "DELETE FROM sources WHERE source_path = ?", (stale_source,)
                    )
            set_metadata(
                connection,
                {
                    "index_schema": INDEX_SCHEMA,
                    "index_version": INDEX_VERSION,
                    "config_identity": config_identity,
                    "project_root": str(project_root),
                },
            )
            for path, source_sha, profile_hash, profile_source, chunks in prepared_groups:
                connection.execute(
                    "DELETE FROM chunks WHERE source_path = ?", (str(path),)
                )
                connection.execute(
                    "DELETE FROM sources WHERE source_path = ?", (str(path),)
                )
                if not chunks:
                    continue
                connection.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                    (str(path), source_sha, profile_hash, profile_source, time.time()),
                )
                for record, text, position, chunk_count, vector in chunks:
                    record_key = str(record["key"])
                    chunk_id = sha256(
                        normalized_json(
                            {
                                "source": str(path),
                                "source_sha256": source_sha,
                                "key": record_key,
                                "chunk_index": position,
                            }
                        )
                    )
                    connection.execute(
                        """INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_path, record_key, chunk_index) DO UPDATE SET
                          chunk_id=excluded.chunk_id,
                          source_sha256=excluded.source_sha256,
                          profile_hash=excluded.profile_hash,
                          profile_source=excluded.profile_source,
                          fields_json=excluded.fields_json,
                          line_start=excluded.line_start,
                          line_end=excluded.line_end,
                          byte_start=excluded.byte_start,
                          byte_end=excluded.byte_end,
                          chunk_count=excluded.chunk_count,
                          text=excluded.text,
                          embedding_json=excluded.embedding_json""",
                        (
                            chunk_id,
                            str(path),
                            source_sha,
                            profile_hash,
                            profile_source,
                            record_key,
                            json.dumps(record.get("fields", {}), ensure_ascii=False, sort_keys=True),
                            int(record["line_start"]),
                            int(record["line_end"]),
                            int(record["byte_start"]),
                            int(record["byte_end"]),
                            position,
                            chunk_count,
                            text,
                            json.dumps(vector),
                        ),
                    )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        indexed_chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        indexed_sources = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        connection.close()
    return finish(
        {
            "schema": CLI_SCHEMA,
            "status": "indexed",
            "project_root": str(project_root),
            "index": str(index),
            "backend": config.backend,
            "model": config.model,
            "indexed_sources": indexed_sources,
            "indexed_chunks": indexed_chunks,
            "records": len(records),
            "reset": reset or args.rebuild,
            "diagnostics": path_diagnostics,
        },
        args.output,
    )


def scope_pattern_matches(relative: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(relative, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(relative, pattern[3:])
    )


def path_matches_scope(path: Path, targets: list[Path], patterns: list[str]) -> bool:
    for target in targets:
        if target.is_file() and path == target:
            return True
        if target.is_dir():
            try:
                relative = path.relative_to(target).as_posix()
            except ValueError:
                continue
            if any(scope_pattern_matches(relative, pattern) for pattern in patterns):
                return True
    return False


def relevant_source_paths(
    connection: sqlite3.Connection,
    targets: list[Path],
    patterns: list[str],
) -> list[str]:
    indexed = [row[0] for row in connection.execute("SELECT source_path FROM sources")]
    return sorted(
        value
        for value in indexed
        if path_matches_scope(Path(value), targets, patterns)
    )


def current_semantic_sources(
    mdq: Any,
    paths: list[Path],
) -> tuple[set[str], list[dict[str, Any]]]:
    current: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    for path in paths:
        try:
            document = mdq.read_document(path)
            if document.profile is None:
                if any(item.get("severity") == "error" for item in document.diagnostics):
                    diagnostics.append(
                        diagnostic(
                            "semantic_source_invalid",
                            "error",
                            f"mdq profile is invalid: {path}",
                            path=str(path),
                        )
                    )
                continue
            records, record_diagnostics = mdq.extract_current(document)
            errors = [
                item
                for item in [*document.diagnostics, *record_diagnostics]
                if item.get("severity") == "error"
            ]
            if errors:
                diagnostics.append(
                    diagnostic(
                        "semantic_source_invalid",
                        "error",
                        f"mdq record extraction is invalid: {path}",
                        path=str(path),
                    )
                )
                continue
            if any(
                item.get("key") is not None
                and float(item.get("confidence", 0.0)) >= 0.6
                for item in records
            ):
                current.add(str(path.resolve()))
        except (OSError, UnicodeDecodeError, TimeoutError) as exc:
            diagnostics.append(
                diagnostic(
                    "semantic_source_invalid",
                    "error",
                    f"could not read Markdown source {path}: {exc}",
                    path=str(path),
                )
            )
    return current, diagnostics


def validate_index_sources(
    mdq: Any,
    connection: sqlite3.Connection,
    source_paths: list[str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for value in source_paths:
        path = Path(value)
        if not path.is_file():
            diagnostics.append(
                diagnostic(
                    "semantic_index_stale",
                    "error",
                    f"indexed source is missing: {path}",
                    path=str(path),
                )
            )
            continue
        row = connection.execute(
            "SELECT source_sha256, profile_hash, profile_source FROM sources WHERE source_path = ?",
            (value,),
        ).fetchone()
        if row is None:
            continue
        try:
            source_sha, profile_hash, profile_source = source_details(mdq, path)
        except (SemanticError, OSError, UnicodeDecodeError, TimeoutError) as exc:
            diagnostics.append(
                diagnostic("semantic_index_stale", "error", str(exc), path=str(path))
            )
            continue
        if (source_sha, profile_hash, profile_source) != tuple(row):
            diagnostics.append(
                diagnostic(
                    "semantic_index_stale",
                    "error",
                    f"source or mdq profile changed since indexing: {path}",
                    path=str(path),
                )
            )
    return diagnostics


def verify_record(mdq: Any, item: IndexedRecord) -> VerifiedRecord | None:
    try:
        document = mdq.read_document(Path(item.source_path))
        records, diagnostics = mdq.extract_current(document)
    except (OSError, UnicodeDecodeError, SemanticError):
        return None
    if any(entry.get("severity") == "error" for entry in diagnostics):
        return None
    matches = [
        record
        for record in records
        if record.get("key") == item.record_key
        and int(record.get("byte_start", -1)) == item.byte_start
        and int(record.get("byte_end", -1)) == item.byte_end
    ]
    if (
        len(matches) != 1
        or document.profile_hash is None
        or document.profile_source is None
        or document.source_hash != item.source_sha256
        or document.profile_hash != item.profile_hash
        or document.profile_source != item.profile_source
    ):
        return None
    return VerifiedRecord(
        record=matches[0],
        source_sha256=document.source_hash,
        profile_hash=document.profile_hash,
        profile_source=document.profile_source,
    )


def parse_where(values: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise SemanticError(f"--where must use FIELD=VALUE syntax: {value}")
        name, expected = value.split("=", 1)
        if not name.strip():
            raise SemanticError(f"--where field must not be empty: {value}")
        result.append((name.strip(), expected))
    return result


def command_query(args: argparse.Namespace) -> int:
    project_root = detect_project_root(args.project_root)
    config = resolve_config(project_root)
    assert config is not None
    index = index_path(project_root, config)
    scope_targets = [
        resolve_user_path(project_root, item) for item in args.path
    ] or [project_root]
    scope_patterns = args.glob or [DEFAULT_GLOB]
    paths, path_diagnostics = normalize_targets(project_root, args.path, args.glob)
    if any(item["severity"] == "error" for item in path_diagnostics):
        return finish(
            {"schema": "mdq.semantic.query.v1", "status": "invalid", "diagnostics": path_diagnostics},
            args.output,
            3,
        )
    if not index.is_file():
        return finish(
            {
                "schema": "mdq.semantic.query.v1",
                "status": "invalid",
                "diagnostics": [
                    diagnostic(
                        "semantic_index_missing",
                        "error",
                        f"semantic index is missing: {index}; run mdq-semantic index first",
                    )
                ],
            },
            args.output,
            3,
        )
    mdq = load_mdq_module()
    connection = open_database(index)
    try:
        metadata = get_metadata(connection)
        if (
            metadata.get("index_schema") != INDEX_SCHEMA
            or metadata.get("index_version") != INDEX_VERSION
            or metadata.get("config_identity") != config.identity
            or metadata.get("project_root") != str(project_root)
        ):
            return finish(
                {
                    "schema": "mdq.semantic.query.v1",
                    "status": "stale",
                    "diagnostics": [
                        diagnostic(
                            "semantic_index_stale",
                            "error",
                            "semantic index configuration differs; rerun mdq-semantic index",
                        )
                    ],
                },
                args.output,
                3,
            )
        source_paths = relevant_source_paths(
            connection, scope_targets, scope_patterns
        )
        current_paths, current_diagnostics = current_semantic_sources(mdq, paths)
        indexed_paths = set(source_paths)
        stale = validate_index_sources(mdq, connection, source_paths)
        if current_diagnostics or current_paths != indexed_paths:
            stale.extend(current_diagnostics)
            stale.append(
                diagnostic(
                    "semantic_index_incomplete",
                    "error",
                    "the indexed Markdown scope differs from the current scope; rerun mdq-semantic index",
                    expected=sorted(indexed_paths),
                    actual=sorted(current_paths),
                )
            )
        if stale:
            return finish(
                {
                    "schema": "mdq.semantic.query.v1",
                    "status": "stale",
                    "query": args.text,
                    "stale_sources": len(stale),
                    "diagnostics": path_diagnostics + stale,
                },
                args.output,
                3,
            )
        rows = connection.execute(
            """SELECT source_path, source_sha256, profile_hash, profile_source,
                      record_key, fields_json, line_start, line_end, byte_start,
                      byte_end, chunk_index, chunk_count, text, embedding_json
               FROM chunks"""
        ).fetchall()
    finally:
        connection.close()
    source_set = set(source_paths)
    where = parse_where(args.where)
    embed = embedding_backend(config)
    query_embeddings = embed([args.text])
    if len(query_embeddings) != 1:
        raise SemanticError("semantic backend returned the wrong query embedding count")
    query_vector = query_embeddings[0]
    candidates: list[tuple[float, IndexedRecord]] = []
    for row in rows:
        item = IndexedRecord(
            source_path=row[0],
            source_sha256=row[1],
            profile_hash=row[2],
            profile_source=row[3],
            record_key=row[4],
            fields=json.loads(row[5]),
            line_start=int(row[6]),
            line_end=int(row[7]),
            byte_start=int(row[8]),
            byte_end=int(row[9]),
            chunk_index=int(row[10]),
            chunk_count=int(row[11]),
            text=row[12],
            embedding=[float(value) for value in json.loads(row[13])],
        )
        if item.source_path not in source_set:
            continue
        if args.id and item.record_key not in set(args.id):
            continue
        candidates.append((cosine(query_vector, item.embedding), item))
    candidates.sort(key=lambda value: (-value[0], value[1].source_path, value[1].record_key))
    mdq = load_mdq_module()
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    verification_diagnostics: list[dict[str, Any]] = []
    for similarity, item in candidates:
        identity = (item.source_path, item.record_key)
        if identity in seen:
            continue
        verified = verify_record(mdq, item)
        if verified is None:
            verification_diagnostics.append(
                diagnostic(
                    "semantic_record_not_verified",
                    "warning",
                    f"semantic candidate could not be revalidated by mdq: {item.record_key}",
                    path=item.source_path,
                )
            )
            continue
        seen.add(identity)
        current = verified.record
        fields = current.get("fields", {})
        if args.id and current.get("key") not in set(args.id):
            continue
        if any(str(fields.get(name)) != expected for name, expected in where):
            continue
        records.append(
            {
                "key": current.get("key"),
                "title": fields.get("title"),
                "fields": fields,
                "similarity": round(float(similarity), 6),
                "snippet": item.text,
                "document": item.source_path,
                "relative_path": relative_to_project(Path(item.source_path), project_root),
                "line_start": current.get("line_start"),
                "line_end": current.get("line_end"),
                "byte_start": current.get("byte_start"),
                "byte_end": current.get("byte_end"),
                "confidence": current.get("confidence"),
                "profile_source": verified.profile_source,
            }
        )
        if len(records) >= args.top_k:
            break
    diagnostics = path_diagnostics + verification_diagnostics
    status = "matched" if records else "not_found"
    if not records:
        diagnostics.append(
            diagnostic("no_match", "info", f"no semantic record matched {args.text!r}")
        )
    return finish(
        {
            "schema": "mdq.semantic.query.v1",
            "status": status,
            "query": args.text,
            "count": len(records),
            "top_k": args.top_k,
            "records": records,
            "diagnostics": diagnostics,
        },
        args.output,
    )


def command_status(args: argparse.Namespace) -> int:
    project_root = detect_project_root(args.project_root)
    config = resolve_config(project_root, required=False)
    if config is None:
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "unconfigured",
                "project_root": str(project_root),
                "diagnostics": [
                    diagnostic(
                        "semantic_backend_unconfigured",
                        "info",
                        "run mdq-semantic configure before indexing or querying",
                    )
                ],
            },
            args.output,
        )
    index = index_path(project_root, config)
    if not index.is_file():
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "not_indexed",
                "project_root": str(project_root),
                "config": str(config.path),
                "index": str(index),
                "backend": config.backend,
                "model": config.model,
                "diagnostics": [],
            },
            args.output,
        )
    scope_targets = [
        resolve_user_path(project_root, item) for item in args.path
    ] or [project_root]
    scope_patterns = args.glob or [DEFAULT_GLOB]
    paths, path_diagnostics = normalize_targets(project_root, args.path, args.glob)
    mdq = load_mdq_module()
    connection = open_database(index)
    try:
        metadata = get_metadata(connection)
        source_count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        source_paths = relevant_source_paths(
            connection, scope_targets, scope_patterns
        )
        current_paths, current_diagnostics = current_semantic_sources(mdq, paths)
        indexed_paths = set(source_paths)
        diagnostics = path_diagnostics + current_diagnostics
        if (
            metadata.get("index_schema") != INDEX_SCHEMA
            or metadata.get("index_version") != INDEX_VERSION
            or metadata.get("config_identity") != config.identity
            or metadata.get("project_root") != str(project_root)
        ):
            diagnostics.append(
                diagnostic(
                    "semantic_index_stale",
                    "error",
                    "semantic index configuration differs; rerun mdq-semantic index",
                )
            )
        diagnostics.extend(validate_index_sources(mdq, connection, source_paths))
        if current_paths != indexed_paths:
            diagnostics.append(
                diagnostic(
                    "semantic_index_incomplete",
                    "error",
                    "the indexed Markdown scope differs from the current scope; rerun mdq-semantic index",
                    expected=sorted(indexed_paths),
                    actual=sorted(current_paths),
                )
            )
    finally:
        connection.close()
    status = "ready" if not any(item["severity"] == "error" for item in diagnostics) else "stale"
    return finish(
        {
            "schema": CLI_SCHEMA,
            "status": status,
            "project_root": str(project_root),
            "config": str(config.path),
            "index": str(index),
            "backend": config.backend,
            "model": config.model,
            "indexed_sources": source_count,
            "indexed_chunks": chunk_count,
            "stale_sources": len(
                [item for item in diagnostics if item.get("code") == "semantic_index_stale"]
            ),
            "diagnostics": diagnostics,
        },
        args.output,
    )


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", help="project root; defaults to Git root or cwd")
    parser.add_argument("--output", choices=("json", "compact"), default="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index and query mdq-governed Markdown records with local embeddings."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure", help="configure a semantic backend")
    add_common_options(configure_parser)
    configure_parser.add_argument("--backend", choices=("omlx", "ollama", "api"))
    configure_parser.add_argument("--model")
    configure_parser.add_argument("--base-url")
    configure_parser.add_argument("--api-key-env")
    configure_parser.add_argument("--index", default=".mdq/semantic/index.sqlite3")
    configure_parser.add_argument("--global", dest="global_config", action="store_true")
    configure_parser.set_defaults(handler=configure)

    index_parser = subparsers.add_parser("index", help="build or refresh a semantic index")
    index_parser.add_argument("path", nargs="+", help="Markdown files or directories")
    add_common_options(index_parser)
    index_parser.add_argument("--glob", action="append")
    index_parser.add_argument("--rebuild", action="store_true")
    index_parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    index_parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    index_parser.add_argument("--batch-size", type=int, default=32)
    index_parser.set_defaults(handler=command_index)

    query_parser = subparsers.add_parser("query", help="retrieve semantically related records")
    query_parser.add_argument("path", nargs="*", help="Markdown files or directories; default is project root")
    add_common_options(query_parser)
    query_parser.add_argument("--glob", action="append")
    query_parser.add_argument("--text", required=True, help="natural-language query")
    query_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    query_parser.add_argument("--id", action="append")
    query_parser.add_argument("--where", action="append", default=[])
    query_parser.set_defaults(handler=command_query)

    status_parser = subparsers.add_parser("status", help="show semantic configuration and index status")
    status_parser.add_argument("path", nargs="*", help="Markdown files or directories; default is project root")
    add_common_options(status_parser)
    status_parser.add_argument("--glob", action="append")
    status_parser.set_defaults(handler=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "top_k", DEFAULT_TOP_K) < 1 or getattr(args, "top_k", DEFAULT_TOP_K) > MAX_TOP_K:
        parser.error(f"--top-k must be between 1 and {MAX_TOP_K}")
    if getattr(args, "batch_size", 1) < 1:
        parser.error("--batch-size must be at least 1")
    if getattr(args, "chunk_chars", DEFAULT_CHUNK_CHARS) < 1:
        parser.error("--chunk-chars must be at least 1")
    if getattr(args, "chunk_overlap", DEFAULT_CHUNK_OVERLAP) < 0:
        parser.error("--chunk-overlap must not be negative")
    try:
        return int(args.handler(args))
    except SemanticError as exc:
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "invalid",
                "diagnostics": [diagnostic("semantic_cli_error", "error", str(exc))],
            },
            getattr(args, "output", "json"),
            3,
        )
    except sqlite3.DatabaseError as exc:
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "invalid",
                "diagnostics": [
                    diagnostic(
                        "semantic_index_invalid",
                        "error",
                        f"semantic index is not a valid SQLite database: {exc}",
                    )
                ],
            },
            getattr(args, "output", "json"),
            3,
        )
    except KeyboardInterrupt:
        return finish(
            {
                "schema": CLI_SCHEMA,
                "status": "interrupted",
                "diagnostics": [diagnostic("semantic_cli_interrupted", "error", "operation interrupted")],
            },
            getattr(args, "output", "json"),
            130,
        )


if __name__ == "__main__":
    raise SystemExit(main())
