#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "markdown-it-py>=4,<5",
#   "PyYAML>=6,<7",
#   "regex>=2024.11.6",
# ]
# ///
"""Fault-tolerant, source-located queries for imperfect Markdown documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import regex as profile_regex
import yaml
from markdown_it import MarkdownIt


ENGINE = "mdq.py/3"
INDEX_SCHEMA = 1
MAX_PROFILE_BYTES = 64 * 1024
MAX_PATTERN_LENGTH = 512
MAX_REGEX_LINE = 8 * 1024
REGEX_TIMEOUT_SECONDS = 0.05
PROFILE_COMMENT_RE = re.compile(
    r"<!--[ \t]*mdq[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?[ \t]*-->", re.DOTALL
)
MARKER_RE = re.compile(
    r"<!--[ \t]*mdq:record[ \t]+id[ \t]*=[ \t]*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))[ \t]*-->",
    re.IGNORECASE,
)
ATX_HEADING_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
SETEXT_RE = re.compile(r"^[ \t]{0,3}(=+|-+)[ \t]*$")
GENERIC_ID_PATTERN = r"[A-Za-z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)*-[0-9]+"
GENERIC_ID_RE = re.compile(rf"\b({GENERIC_ID_PATTERN})\b")
TEMPORARY_PROFILE_PREFIX = "temporary-"
TEMPORARY_GENERIC_KEY_PATTERN = (
    rf"^[ \t]*(?P<id>{GENERIC_ID_PATTERN})"
    r"(?=$|[ \t:：—–-])"
)
YAML_MDQ_DECLARATION_RE = re.compile(r"(?m)^mdq[ \t]*:")
TOML_MDQ_DECLARATION_RE = re.compile(r"(?m)^(?:mdq[ \t]*=|\[mdq(?:\.|\]))")
INFERRED_KEY_LABELS = {
    "id",
    "key",
    "identifier",
    "recordid",
    "requirementid",
    "reqid",
    "ticketid",
    "编号",
    "标识",
    "标识符",
    "需求id",
    "需求编号",
    "唯一键",
}


class DuplicateKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""

    def compose_node(self, parent: yaml.Node | None, index: int | None) -> yaml.Node:
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            mark = getattr(event, "start_mark", None)
            raise yaml.constructor.ConstructorError(
                "while composing a profile",
                mark,
                "YAML aliases are not allowed in mdq profiles",
                mark,
            )
        return super().compose_node(parent, index)


def _construct_unique_mapping(
    loader: DuplicateKeyLoader, node: yaml.Node, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found an unhashable key: {exc}",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    line: int | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if line is not None:
        item["line"] = line
    if details is not None:
        item["details"] = details
    return item


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def actionable_diagnostics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(payload.get("diagnostics", []))
    for record in payload.get("records", []):
        items.extend(record.get("diagnostics", []))
    return [
        item
        for item in items
        if item.get("severity") in {"warning", "error"}
    ]


def minimal_query_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    records = payload.get("records", [])
    if (
        payload.get("status") != "matched"
        or payload.get("count") != 1
        or len(records) != 1
        or payload.get("candidates")
        or actionable_diagnostics(payload)
    ):
        return None
    record = records[0]
    minimal: dict[str, Any] = {
        "status": "matched",
        "count": 1,
        "key": record.get("key"),
        "fields": record.get("fields", {}),
        "line_start": record.get("line_start"),
        "line_end": record.get("line_end"),
        "confidence": record.get("confidence"),
    }
    diagnostic_codes = [
        item.get("code")
        for item in payload.get("diagnostics", [])
        if item.get("code")
    ]
    if diagnostic_codes:
        minimal["diagnostics"] = diagnostic_codes
    return minimal


def emit_query_result(payload: dict[str, Any], output: str) -> int | None:
    if output == "json":
        emit(payload)
        return None
    if output == "minimal":
        emit(minimal_query_payload(payload) or payload)
        return None

    records = payload.get("records", [])
    reason: str | None = None
    if (
        payload.get("status") != "matched"
        or payload.get("count") != 1
        or len(records) != 1
    ):
        reason = "raw output requires exactly one matched record"
    elif payload.get("candidates"):
        reason = "raw output refuses to hide alternate candidate evidence"
    elif actionable_diagnostics(payload):
        reason = "raw output refuses to hide warning or error diagnostics"
    else:
        raw = records[0].get("fields", {}).get("raw")
        if not isinstance(raw, str):
            reason = "raw output requires the matched record to declare a string field named 'raw'"
        else:
            sys.stdout.write(raw)
            if not raw.endswith("\n"):
                sys.stdout.write("\n")
            return None

    failure = dict(payload)
    failure["diagnostics"] = list(payload.get("diagnostics", [])) + [
        diagnostic("raw_output_unavailable", "error", reason)
    ]
    emit(failure)
    return 5


def normalized_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=DuplicateKeyLoader)


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def top_level_json_key_present(text: str, wanted: str) -> bool:
    """Conservatively find a top-level key even when the JSON is malformed."""
    cursor = 0
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor >= len(text) or text[cursor] != "{":
        return False
    brace_depth = 1
    bracket_depth = 0
    expecting_key = True
    cursor += 1
    while cursor < len(text):
        char = text[cursor]
        if char.isspace():
            cursor += 1
            continue
        if char in {'"', "'"}:
            quote = char
            start = cursor
            cursor += 1
            escaped = False
            while cursor < len(text):
                current = text[cursor]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
                cursor += 1
            if cursor >= len(text):
                return False
            token = text[start : cursor + 1]
            value: str | None = None
            if quote == '"':
                try:
                    decoded = json.loads(token)
                    value = decoded if isinstance(decoded, str) else None
                except json.JSONDecodeError:
                    value = token[1:-1]
            else:
                value = token[1:-1]
            cursor += 1
            lookahead = cursor
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if (
                brace_depth == 1
                and bracket_depth == 0
                and expecting_key
                and lookahead < len(text)
                and text[lookahead] == ":"
            ):
                if value == wanted:
                    return True
                expecting_key = False
            continue
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth <= 0:
                return False
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        elif char == "," and brace_depth == 1 and bracket_depth == 0:
            expecting_key = True
        elif expecting_key and brace_depth == 1 and bracket_depth == 0:
            end = cursor
            while end < len(text) and text[end] not in ":,{}[]\r\n":
                end += 1
            if end < len(text) and text[end] == ":":
                if text[cursor:end].strip() == wanted:
                    return True
                expecting_key = False
                cursor = end
        cursor += 1
    return False


def normalize_label(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^(?:\*\*|__|`)+|(?:\*\*|__|`)+$", "", value).strip()
    return re.sub(r"\s+", "", value).casefold()


def field_name_from_header(value: str, position: int) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return name or f"column_{position + 1}"


def safe_compile(
    pattern: str, where: str, diagnostics: list[dict[str, Any]]
) -> profile_regex.Pattern[str] | None:
    if not isinstance(pattern, str):
        diagnostics.append(
            diagnostic("profile_invalid", "error", f"{where} must be a string")
        )
        return None
    if len(pattern) > MAX_PATTERN_LENGTH:
        diagnostics.append(
            diagnostic(
                "profile_invalid",
                "error",
                f"{where} exceeds {MAX_PATTERN_LENGTH} characters",
            )
        )
        return None
    try:
        return profile_regex.compile(pattern, profile_regex.VERSION0)
    except profile_regex.error as exc:
        diagnostics.append(
            diagnostic("profile_invalid", "error", f"{where} is invalid: {exc}")
        )
        return None


def validate_group(
    compiled: profile_regex.Pattern[str] | None,
    group: str | int | None,
    where: str,
    diagnostics: list[dict[str, Any]],
) -> None:
    if group is None or compiled is None:
        return
    if isinstance(group, str) and group.isdigit():
        group = int(group)
    if isinstance(group, int):
        if group < 0 or group > compiled.groups:
            diagnostics.append(
                diagnostic(
                    "profile_invalid",
                    "error",
                    f"{where} references capture group {group}, but pattern has {compiled.groups}",
                )
            )
    elif group not in compiled.groupindex:
        diagnostics.append(
            diagnostic(
                "profile_invalid",
                "error",
                f"{where} references missing named capture group {group!r}",
            )
        )


def match_group(match: re.Match[str], group: str | int | None) -> str | None:
    if group is None:
        return match.group(0).strip()
    if isinstance(group, str) and group.isdigit():
        group = int(group)
    try:
        value = match.group(group)
    except (IndexError, KeyError):
        return None
    return value.strip() if value is not None else None


@dataclass
class ProfileLoad:
    profile: dict[str, Any] | None
    source: str | None
    excluded_lines: set[int]
    diagnostics: list[dict[str, Any]]


@dataclass
class SourceDocument:
    path: Path
    raw: bytes
    text: str
    lines: list[str]
    masked_text: str
    masked_lines: list[str]
    lexical_code_lines: set[int]
    unclosed_fence_line: int | None
    unclosed_comment_line: int | None
    unclosed_opaque_blocks: list[tuple[int, str]]
    byte_offsets: list[int]
    profile: dict[str, Any] | None
    profile_source: str | None
    excluded_lines: set[int]
    diagnostics: list[dict[str, Any]]

    @property
    def source_hash(self) -> str:
        return sha256(self.raw)

    @property
    def profile_hash(self) -> str | None:
        return (
            sha256(normalized_json(self.profile)) if self.profile is not None else None
        )


@dataclass
class Heading:
    start: int
    end: int
    level: int
    text: str
    source: str


@dataclass
class Marker:
    line: int
    key: str


@dataclass
class TableRow:
    start: int
    end: int
    values: list[str]
    cells: dict[str, str]


@dataclass
class MarkdownTable:
    start: int
    end: int
    header_line: int
    headers: list[str]
    rows: list[TableRow]
    under_heading: str | None


@dataclass
class Record:
    key: str | None
    start: int
    end: int
    heading: Heading | None
    marker: Marker | None
    table_row: TableRow | None
    fields: dict[str, Any]
    confidence: float
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    identity_evidence: list[dict[str, Any]] = field(default_factory=list)


def line_set(start: int, end: int) -> set[int]:
    return set(range(max(0, start), max(start, end)))


def parse_profile(text: str, lines: list[str]) -> ProfileLoad:
    diagnostics: list[dict[str, Any]] = []
    excluded: set[int] = set()
    found: list[tuple[str, dict[str, Any]]] = []
    allowed_comment_anchors = [0]

    first = lines[0].lstrip("\ufeff").strip() if lines else ""
    if first in {"---", "+++"}:
        delimiter = first
        closing: int | None = None
        for index in range(1, len(lines)):
            valid_closers = {"---", "..."} if delimiter == "---" else {"+++"}
            if lines[index].strip() in valid_closers:
                closing = index
                break
        if closing is None:
            diagnostics.append(
                diagnostic(
                    "frontmatter_incomplete",
                    "warning",
                    f"{delimiter} frontmatter has no closing delimiter",
                    line=1,
                )
            )
            if delimiter == "---" and YAML_MDQ_DECLARATION_RE.search(
                "".join(lines[1:])[:MAX_PROFILE_BYTES]
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "incomplete YAML frontmatter appears to declare mdq; refusing temporary inference",
                        line=1,
                    )
                )
            elif delimiter == "+++" and TOML_MDQ_DECLARATION_RE.search(
                "".join(lines[1:])[:MAX_PROFILE_BYTES]
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_unsupported",
                        "error",
                        "mdq contracts must use YAML Front Matter delimited by ---",
                        line=1,
                    )
                )
        else:
            excluded |= line_set(0, closing + 1)
            allowed_comment_anchors.append(
                sum(len(line) for line in lines[: closing + 1])
            )
            if delimiter == "---":
                try:
                    root = load_yaml("".join(lines[1:closing])) or {}
                    if isinstance(root, dict) and "mdq" in root:
                        if isinstance(root["mdq"], dict):
                            found.append(("yaml-frontmatter", root["mdq"]))
                        else:
                            diagnostics.append(
                                diagnostic(
                                    "profile_invalid",
                                    "error",
                                    "frontmatter mdq value must be a mapping",
                                    line=1,
                                )
                            )
                except (yaml.YAMLError, TypeError, ValueError, RecursionError) as exc:
                    diagnostics.append(
                        diagnostic(
                            "frontmatter_invalid",
                            "warning",
                            f"frontmatter could not be parsed: {exc}",
                            line=1,
                        )
                    )
                    if YAML_MDQ_DECLARATION_RE.search("".join(lines[1:closing])):
                        diagnostics.append(
                            diagnostic(
                                "profile_invalid",
                                "error",
                                "invalid YAML frontmatter appears to declare mdq; refusing temporary inference",
                                line=1,
                            )
                        )
            elif TOML_MDQ_DECLARATION_RE.search("".join(lines[1:closing])):
                diagnostics.append(
                    diagnostic(
                        "profile_unsupported",
                        "error",
                        "mdq contracts must use YAML Front Matter delimited by ---",
                        line=1,
                    )
                )
    else:
        stripped = text.lstrip("\ufeff \t\r\n")
        if stripped.startswith("{"):
            leading = len(text) - len(stripped)
            try:
                decoder = json.JSONDecoder(object_pairs_hook=unique_json_object)
                root, end = decoder.raw_decode(stripped)
                if not isinstance(root, dict):
                    raise ValueError("JSON frontmatter must be an object")
                closing_char = leading + end
                closing_line = text.count("\n", 0, closing_char)
                excluded |= line_set(0, closing_line + 1)
                allowed_comment_anchors.append(closing_char)
                if "mdq" in root:
                    diagnostics.append(
                        diagnostic(
                            "profile_unsupported",
                            "error",
                            "mdq contracts must use YAML Front Matter delimited by ---",
                            line=1,
                        )
                    )
            except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
                diagnostics.append(
                    diagnostic(
                        "frontmatter_invalid",
                        "warning",
                        f"JSON frontmatter could not be parsed: {exc}",
                        line=1,
                    )
                )
                if top_level_json_key_present(stripped[:MAX_PROFILE_BYTES], "mdq"):
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "invalid JSON frontmatter appears to declare mdq; refusing temporary inference",
                            line=1,
                        )
                    )

    prefix = text[:MAX_PROFILE_BYTES]
    for match in PROFILE_COMMENT_RE.finditer(prefix):
        allowed = any(
            not text[anchor : match.start()].lstrip("\ufeff").strip()
            for anchor in allowed_comment_anchors
            if anchor <= match.start()
        )
        if not allowed:
            continue
        start_line = text.count("\n", 0, match.start())
        end_line = text.count("\n", 0, match.end()) + 1
        excluded |= line_set(start_line, end_line)
        diagnostics.append(
            diagnostic(
                "profile_unsupported",
                "error",
                "mdq HTML comment contracts are unsupported; move the profile to YAML Front Matter",
                line=start_line + 1,
            )
        )

    if len(found) > 1:
        diagnostics.append(
            diagnostic(
                "profile_conflict",
                "error",
                "multiple mdq profiles are present; remove one instead of relying on precedence",
                details={"sources": [source for source, _ in found]},
            )
        )
        return ProfileLoad(None, None, excluded, diagnostics)
    if not found:
        if not any(
            item["code"] in {"profile_invalid", "profile_unsupported"}
            for item in diagnostics
        ):
            diagnostics.append(
                diagnostic(
                    "profile_missing",
                    "info",
                    "no mdq profile found; profile-free read-only queries remain available",
                )
            )
        return ProfileLoad(None, None, excluded, diagnostics)
    source, profile = found[0]
    validated = validate_profile(profile, diagnostics)
    return ProfileLoad(validated, source, excluded, diagnostics)


def _unknown_keys(
    mapping: dict[str, Any],
    allowed: set[str],
    where: str,
    diagnostics: list[dict[str, Any]],
) -> None:
    for key in mapping:
        if not isinstance(key, str) or (
            key not in allowed and not key.startswith("x-")
        ):
            diagnostics.append(
                diagnostic("profile_invalid", "error", f"unknown key {where}.{key}")
            )


def _string_list(
    value: Any, where: str, diagnostics: list[dict[str, Any]]
) -> list[str] | None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        diagnostics.append(
            diagnostic(
                "profile_invalid", "error", f"{where} must be a non-empty string list"
            )
        )
        return None
    return value


def _positive_int(value: Any, where: str, diagnostics: list[dict[str, Any]]) -> None:
    if type(value) is not int or value < 1:
        diagnostics.append(
            diagnostic(
                "profile_invalid", "error", f"{where} must be a positive integer"
            )
        )


def _validate_queries(
    queries: Any,
    fields: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    if not isinstance(queries, dict) or not queries:
        diagnostics.append(
            diagnostic(
                "profile_invalid", "error", "queries must be a non-empty mapping"
            )
        )
        return
    for name, spec in queries.items():
        where = f"mdq.queries.{name}"
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            diagnostics.append(
                diagnostic(
                    "profile_invalid", "error", f"{where} must be a named mapping"
                )
            )
            continue
        _unknown_keys(spec, {"when", "match", "select", "expect"}, where, diagnostics)
        when = spec.get("when")
        if when is not None:
            if not isinstance(when, dict):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid", "error", f"{where}.when must be a mapping"
                    )
                )
            else:
                _unknown_keys(when, {"pattern"}, f"{where}.when", diagnostics)
                if "pattern" not in when:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"{where}.when.pattern is required",
                        )
                    )
                else:
                    safe_compile(when["pattern"], f"{where}.when.pattern", diagnostics)
        match = spec.get("match")
        if not isinstance(match, dict):
            diagnostics.append(
                diagnostic(
                    "profile_invalid", "error", f"{where}.match must be a mapping"
                )
            )
        else:
            _unknown_keys(
                match, {"source", "field", "operator"}, f"{where}.match", diagnostics
            )
            source = match.get("source")
            operator = match.get("operator", "eq")
            if source not in {"key", "field"}:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"{where}.match.source must be key or field",
                    )
                )
            if operator not in {"eq", "contains"}:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"{where}.match.operator must be eq or contains",
                    )
                )
            if source == "field":
                field_name = match.get("field")
                if not isinstance(field_name, str) or field_name not in fields:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"{where}.match.field must name a declared field",
                        )
                    )
            elif "field" in match:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"{where}.match.field is only valid for field queries",
                    )
                )
        if "select" in spec:
            selected = _string_list(spec["select"], f"{where}.select", diagnostics)
            if selected:
                unknown = [item for item in selected if item not in fields]
                if unknown:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"{where}.select references undeclared fields",
                            details={"fields": unknown},
                        )
                    )
        expect = spec.get("expect", {})
        if not isinstance(expect, dict):
            diagnostics.append(
                diagnostic(
                    "profile_invalid", "error", f"{where}.expect must be a mapping"
                )
            )
        else:
            active_limits = {
                "max_record_lines",
                "max_record_bytes",
                "max_total_bytes",
            }
            allowed = active_limits | {
                "max_matches",
                "structured",
                "min_confidence",
            }
            _unknown_keys(expect, allowed, f"{where}.expect", diagnostics)
            for key in active_limits | {"max_matches"}:
                if key in expect:
                    _positive_int(expect[key], f"{where}.expect.{key}", diagnostics)
            if "max_matches" in expect:
                diagnostics.append(
                    diagnostic(
                        "query_max_matches_deprecated",
                        "info",
                        f"{where}.expect.max_matches is ignored; "
                        "use payload limits for result-size budgets",
                    )
                )
            if "structured" in expect and not isinstance(expect["structured"], bool):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"{where}.expect.structured must be boolean",
                    )
                )
            if "min_confidence" in expect and (
                not isinstance(expect["min_confidence"], (int, float))
                or isinstance(expect["min_confidence"], bool)
                or not 0 <= float(expect["min_confidence"]) <= 1
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"{where}.expect.min_confidence must be between 0 and 1",
                    )
                )


def validate_profile(
    profile: dict[str, Any], diagnostics: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        diagnostics.append(
            diagnostic("profile_invalid", "error", "profile must be a mapping")
        )
        return None
    try:
        serialized_profile = json.dumps(profile, ensure_ascii=False)
        if len(serialized_profile.encode("utf-8")) > MAX_PROFILE_BYTES:
            diagnostics.append(
                diagnostic(
                    "profile_invalid",
                    "error",
                    f"expanded profile exceeds {MAX_PROFILE_BYTES} bytes",
                )
            )
            return None
        profile = json.loads(serialized_profile)
    except (TypeError, ValueError, RecursionError) as exc:
        diagnostics.append(
            diagnostic(
                "profile_invalid",
                "error",
                f"profile values must be JSON-compatible: {exc}",
            )
        )
        return None
    version = profile.get("version")
    allowed_top = {"version", "dialect", "records", "fields", "tolerance", "index"}
    if version == 2:
        allowed_top |= {"actors", "queries", "maintenance"}
    _unknown_keys(profile, allowed_top, "mdq", diagnostics)
    if type(version) is not int or version not in {1, 2}:
        diagnostics.append(
            diagnostic(
                "profile_unsupported",
                "error",
                "only mdq versions 1 and 2 are supported",
            )
        )

    dialect = profile.setdefault("dialect", "commonmark")
    if dialect not in {"commonmark", "gfm"}:
        diagnostics.append(
            diagnostic("profile_invalid", "error", "dialect must be commonmark or gfm")
        )

    key_pattern_compiled: profile_regex.Pattern[str] | None = None
    boundary_source: str | None = None
    records = profile.get("records")
    if not isinstance(records, dict):
        diagnostics.append(
            diagnostic("profile_invalid", "error", "records must be a mapping")
        )
    else:
        _unknown_keys(records, {"boundary", "key"}, "mdq.records", diagnostics)
        boundary = records.get("boundary")
        if not isinstance(boundary, dict):
            diagnostics.append(
                diagnostic(
                    "profile_invalid", "error", "records.boundary must be a mapping"
                )
            )
        else:
            boundary_source = boundary.setdefault("source", "heading")
            boundary_keys = {"source", "levels", "level_tolerance", "pattern"}
            if version == 2:
                boundary_keys |= {"under_heading", "columns"}
            _unknown_keys(boundary, boundary_keys, "mdq.records.boundary", diagnostics)
            if version == 1 and boundary_source != "heading":
                diagnostics.append(
                    diagnostic(
                        "profile_invalid", "error", "v1 boundary source must be heading"
                    )
                )
            if version == 2 and boundary_source not in {"heading", "table-row"}:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "v2 boundary source must be heading or table-row",
                    )
                )
            if boundary_source == "heading":
                levels = boundary.get("levels")
                if (
                    not isinstance(levels, list)
                    or not levels
                    or not all(type(x) is int and 1 <= x <= 6 for x in levels)
                ):
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "records.boundary.levels must contain heading levels 1..6",
                        )
                    )
                tolerance = boundary.setdefault("level_tolerance", 0)
                if type(tolerance) is not int or not 0 <= tolerance <= 5:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "records.boundary.level_tolerance must be 0..5",
                        )
                    )
                if "pattern" in boundary:
                    safe_compile(
                        boundary["pattern"], "records.boundary.pattern", diagnostics
                    )
            elif boundary_source == "table-row":
                if dialect != "gfm":
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "table-row boundaries require dialect: gfm",
                        )
                    )
                columns = _string_list(
                    boundary.get("columns"), "records.boundary.columns", diagnostics
                )
                if columns and len(set(columns)) != len(columns):
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "records.boundary.columns must be unique",
                        )
                    )
                under_heading = boundary.get("under_heading")
                if under_heading is not None and (
                    not isinstance(under_heading, str) or not under_heading.strip()
                ):
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "records.boundary.under_heading must be non-empty text",
                        )
                    )
                for incompatible in {"levels", "level_tolerance", "pattern"} & set(
                    boundary
                ):
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"records.boundary.{incompatible} is unavailable for table-row",
                        )
                    )

        key = records.get("key")
        if not isinstance(key, dict):
            diagnostics.append(
                diagnostic("profile_invalid", "error", "records.key must be a mapping")
            )
        else:
            _unknown_keys(
                key,
                {"source", "pattern", "group", "labels", "column"},
                "mdq.records.key",
                diagnostics,
            )
            source = key.get("source", "heading")
            key["source"] = source
            supported_key_sources = {"heading", "label", "marker"}
            if version == 2:
                supported_key_sources.add("column")
            if source not in supported_key_sources:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid", "error", "records.key.source is unsupported"
                    )
                )
            if "pattern" in key:
                key_pattern_compiled = safe_compile(
                    key["pattern"], "records.key.pattern", diagnostics
                )
            if source == "label":
                _string_list(key.get("labels"), "records.key.labels", diagnostics)
            if source == "column" and (
                not isinstance(key.get("column"), str) or not key["column"].strip()
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "records.key.column must be non-empty text",
                    )
                )
            if source == "column" and boundary_source != "table-row":
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "column keys require a table-row boundary",
                    )
                )
            if (
                source == "column"
                and isinstance(records.get("boundary"), dict)
                and isinstance(records["boundary"].get("columns"), list)
                and key.get("column") not in records["boundary"]["columns"]
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "records.key.column must be declared in boundary.columns",
                    )
                )
            if "group" in key and (
                not isinstance(key["group"], (str, int))
                or isinstance(key["group"], bool)
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "records.key.group must be a name or number",
                    )
                )
            elif "group" in key:
                if key_pattern_compiled is None:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "records.key.group requires records.key.pattern",
                        )
                    )
                else:
                    validate_group(
                        key_pattern_compiled,
                        key["group"],
                        "records.key.group",
                        diagnostics,
                    )

    fields = profile.setdefault("fields", {})
    if not isinstance(fields, dict):
        diagnostics.append(
            diagnostic("profile_invalid", "error", "fields must be a mapping")
        )
    else:
        for name, spec in fields.items():
            if not isinstance(name, str) or not name or not isinstance(spec, dict):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"field {name!r} must be a named mapping",
                    )
                )
                continue
            _unknown_keys(
                spec,
                {"source", "pattern", "group", "labels", "headings", "column"},
                f"mdq.fields.{name}",
                diagnostics,
            )
            source = spec.get("source")
            supported_field_sources = {"heading", "label", "section", "body", "regex"}
            if version == 2:
                supported_field_sources.add("column")
            if source not in supported_field_sources:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"field {name} has unsupported source",
                    )
                )
            field_pattern_compiled: profile_regex.Pattern[str] | None = None
            if "pattern" in spec:
                field_pattern_compiled = safe_compile(
                    spec["pattern"], f"fields.{name}.pattern", diagnostics
                )
            if source == "regex" and "pattern" not in spec:
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"field {name} regex source needs pattern",
                    )
                )
            if source == "label":
                _string_list(spec.get("labels"), f"fields.{name}.labels", diagnostics)
            if source == "section":
                _string_list(
                    spec.get("headings"), f"fields.{name}.headings", diagnostics
                )
            if source == "column" and (
                not isinstance(spec.get("column"), str) or not spec["column"].strip()
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"fields.{name}.column must be non-empty text",
                    )
                )
            if source == "column" and boundary_source != "table-row":
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"field {name} column source requires a table-row boundary",
                    )
                )
            if (
                source == "column"
                and isinstance(records, dict)
                and isinstance(records.get("boundary"), dict)
                and isinstance(records["boundary"].get("columns"), list)
                and spec.get("column") not in records["boundary"]["columns"]
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"fields.{name}.column must be declared in boundary.columns",
                    )
                )
            if "group" in spec and (
                not isinstance(spec["group"], (str, int))
                or isinstance(spec["group"], bool)
            ):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        f"field {name} group must be a name or number",
                    )
                )
            elif "group" in spec:
                effective_pattern = (
                    key_pattern_compiled
                    if source == "heading" and "pattern" not in spec
                    else field_pattern_compiled
                )
                if effective_pattern is None:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"field {name} group requires an effective pattern",
                        )
                    )
                else:
                    validate_group(
                        effective_pattern,
                        spec["group"],
                        f"fields.{name}.group",
                        diagnostics,
                    )

    if version == 2 and "actors" in profile:
        actors = profile["actors"]
        if not isinstance(actors, dict):
            diagnostics.append(
                diagnostic("profile_invalid", "error", "actors must be a mapping")
            )
        else:
            _unknown_keys(actors, {"read", "write"}, "mdq.actors", diagnostics)
            for action in ("read", "write"):
                if action in actors and actors[action] not in {
                    "human",
                    "machine",
                    "mixed",
                }:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            f"actors.{action} must be human, machine, or mixed",
                        )
                    )

    if version == 2 and "queries" in profile:
        _validate_queries(
            profile["queries"], fields if isinstance(fields, dict) else {}, diagnostics
        )

    if version == 2 and "maintenance" in profile:
        maintenance = profile["maintenance"]
        if not isinstance(maintenance, dict):
            diagnostics.append(
                diagnostic("profile_invalid", "error", "maintenance must be a mapping")
            )
        else:
            _unknown_keys(
                maintenance, {"query_contract"}, "mdq.maintenance", diagnostics
            )
            policy = maintenance.get("query_contract")
            if not isinstance(policy, dict):
                diagnostics.append(
                    diagnostic(
                        "profile_invalid",
                        "error",
                        "maintenance.query_contract must be a mapping",
                    )
                )
            else:
                _unknown_keys(
                    policy,
                    {"mode", "allow", "max_changes_per_run"},
                    "mdq.maintenance.query_contract",
                    diagnostics,
                )
                mode = policy.get("mode", "propose")
                if mode not in {"locked", "propose", "auto"}:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "maintenance.query_contract.mode must be locked, propose, or auto",
                        )
                    )
                if mode == "auto" and "allow" not in policy:
                    diagnostics.append(
                        diagnostic(
                            "profile_invalid",
                            "error",
                            "maintenance.query_contract.allow is required in auto mode",
                        )
                    )
                if "allow" in policy:
                    allowed = _string_list(
                        policy["allow"], "maintenance.query_contract.allow", diagnostics
                    )
                    if allowed:
                        invalid = [
                            item
                            for item in allowed
                            if item not in {"queries", "fields", "records"}
                        ]
                        if invalid:
                            diagnostics.append(
                                diagnostic(
                                    "profile_invalid",
                                    "error",
                                    "maintenance.query_contract.allow has unsupported scopes",
                                    details={"scopes": invalid},
                                )
                            )
                if "max_changes_per_run" in policy:
                    _positive_int(
                        policy["max_changes_per_run"],
                        "maintenance.query_contract.max_changes_per_run",
                        diagnostics,
                    )

    tolerance = profile.setdefault("tolerance", {"incomplete": False})
    if not isinstance(tolerance, dict):
        diagnostics.append(
            diagnostic("profile_invalid", "error", "tolerance must be a mapping")
        )
    else:
        _unknown_keys(tolerance, {"incomplete"}, "mdq.tolerance", diagnostics)
        incomplete = tolerance.setdefault("incomplete", False)
        if not isinstance(incomplete, bool):
            diagnostics.append(
                diagnostic(
                    "profile_invalid", "error", "tolerance.incomplete must be boolean"
                )
            )

    if "index" in profile and (
        not isinstance(profile["index"], str) or not profile["index"].strip()
    ):
        diagnostics.append(
            diagnostic(
                "profile_invalid", "error", "index must be a non-empty relative path"
            )
        )

    if any(item["severity"] == "error" for item in diagnostics):
        return None
    return profile


def markdown_literal_regions(
    text: str, lines: list[str]
) -> tuple[set[int], int | None, set[tuple[int, int]]]:
    parser = MarkdownIt("commonmark", {"html": False})
    tokens = parser.parse(text)
    block_code_lines: set[int] = set()
    unclosed_fence_line: int | None = None
    literal_comment_positions: set[tuple[int, int]] = set()

    for token in tokens:
        if token.type in {"fence", "code_block"} and token.map:
            start, end = token.map
            block_code_lines |= line_set(start, end)
            if token.type == "fence" and end > start:
                closing_line = lines[end - 1].rstrip("\r\n")
                marker = re.escape(token.markup[0])
                if not re.search(
                    rf"{marker}{{{len(token.markup)},}}[ \t]*$", closing_line
                ):
                    unclosed_fence_line = (
                        start
                        if unclosed_fence_line is None
                        else min(unclosed_fence_line, start)
                    )
        if token.type != "inline" or not token.map:
            continue
        start, end = token.map
        segment_lines = lines[start:end]
        segment = "".join(segment_lines)
        offsets = [0]
        for line in segment_lines:
            offsets.append(offsets[-1] + len(line))
        code_ranges = inline_code_ranges(segment)
        cursor = 0
        while True:
            position = segment.find("<!--", cursor)
            if position < 0:
                break
            if any(begin <= position < finish for begin, finish in code_ranges):
                local_line = max(0, bisect_right(offsets, position) - 1)
                literal_comment_positions.add(
                    (start + local_line, position - offsets[local_line])
                )
            cursor = position + 4
    return block_code_lines, unclosed_fence_line, literal_comment_positions


def parse_document(path: Path, raw: bytes) -> SourceDocument:
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines:
        lines = [""]
    lexical_code, unclosed_fence_line, literal_comments = markdown_literal_regions(
        text, lines
    )
    (
        masked_text,
        masked_lines,
        lexical_code,
        unclosed_comment_line,
        unclosed_opaque_blocks,
    ) = scan_source_layers(lines, lexical_code, literal_comments)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    loaded = parse_profile(text, lines)
    return SourceDocument(
        path=path.resolve(),
        raw=raw,
        text=text,
        lines=lines,
        masked_text=masked_text,
        masked_lines=masked_lines,
        lexical_code_lines=lexical_code,
        unclosed_fence_line=unclosed_fence_line,
        unclosed_comment_line=unclosed_comment_line,
        unclosed_opaque_blocks=unclosed_opaque_blocks,
        byte_offsets=offsets,
        profile=loaded.profile,
        profile_source=loaded.source,
        excluded_lines=loaded.excluded_lines,
        diagnostics=loaded.diagnostics,
    )


def read_document(path: Path) -> SourceDocument:
    return parse_document(path, path.read_bytes())


def inline_code_ranges(line: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(line):
        if line[cursor] != "`":
            cursor += 1
            continue
        end = cursor
        while end < len(line) and line[end] == "`":
            end += 1
        length = end - cursor
        search = end
        closing = -1
        while search < len(line):
            candidate = line.find("`" * length, search)
            if candidate < 0:
                break
            before_same = candidate > 0 and line[candidate - 1] == "`"
            after_same = (
                candidate + length < len(line) and line[candidate + length] == "`"
            )
            if not before_same and not after_same:
                closing = candidate
                break
            search = candidate + length
        if closing < 0:
            cursor = end
            continue
        ranges.append((cursor, closing + length))
        cursor = closing + length
    return ranges


def position_is_literal(
    line: str, position: int, code_ranges: list[tuple[int, int]]
) -> bool:
    if any(start <= position < end for start, end in code_ranges):
        return True
    backslashes = 0
    cursor = position - 1
    while cursor >= 0 and line[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def scan_source_layers(
    lines: list[str],
    block_code_lines: set[int],
    literal_comment_positions: set[tuple[int, int]],
) -> tuple[
    str,
    list[str],
    set[int],
    int | None,
    list[tuple[int, str]],
]:
    masked_lines: list[str] = []
    excluded_lines = set(block_code_lines)
    opaque: tuple[str, re.Pattern[str], int] | None = None
    comment_start: int | None = None
    html_open = re.compile(r"^ {0,3}<(pre|code|script|style)\b[^>]*>", re.IGNORECASE)
    mdx_open = re.compile(r"^ {0,3}<([A-Z][A-Za-z0-9_.:-]*)\b[^>]*>")
    hugo_open = re.compile(r"^ {0,3}\{\{[<%][ \t]*highlight\b.*[>%]\}\}", re.IGNORECASE)

    for index, line in enumerate(lines):
        if opaque is not None:
            excluded_lines.add(index)
            if index not in block_code_lines and opaque[1].search(line):
                opaque = None
            masked_lines.append(line)
            continue

        if comment_start is None:
            if index in block_code_lines:
                masked_lines.append(line)
                continue

            opaque_match = html_open.match(line)
            if opaque_match:
                tag = opaque_match.group(1)
                closing = re.compile(rf"</{re.escape(tag)}[ \t]*>", re.IGNORECASE)
                excluded_lines.add(index)
                if not closing.search(line, opaque_match.end()):
                    opaque = (f"html:{tag.lower()}", closing, index)
                masked_lines.append(line)
                continue
            opaque_match = mdx_open.match(line)
            if opaque_match and not line.rstrip().endswith("/>"):
                tag = opaque_match.group(1)
                closing = re.compile(rf"</{re.escape(tag)}[ \t]*>")
                excluded_lines.add(index)
                if not closing.search(line, opaque_match.end()):
                    opaque = (f"mdx:{tag}", closing, index)
                masked_lines.append(line)
                continue
            opaque_match = hugo_open.match(line)
            if opaque_match:
                closing = re.compile(
                    r"\{\{[<%][ \t]*/highlight[ \t]*[>%]\}\}", re.IGNORECASE
                )
                excluded_lines.add(index)
                if not closing.search(line, opaque_match.end()):
                    opaque = ("hugo:highlight", closing, index)
                masked_lines.append(line)
                continue

        chars = list(line)
        cursor = 0
        if comment_start is not None:
            closing = line.find("-->")
            stop = len(line) if closing < 0 else closing + 3
            for position in range(0, stop):
                if chars[position] not in {"\r", "\n"}:
                    chars[position] = " "
            if closing < 0:
                masked_lines.append("".join(chars))
                continue
            comment_start = None
            cursor = stop

        code_ranges = inline_code_ranges(line)
        while True:
            opening = line.find("<!--", cursor)
            while opening >= 0 and (
                (index, opening) in literal_comment_positions
                or position_is_literal(line, opening, code_ranges)
            ):
                opening = line.find("<!--", opening + 4)
            if opening < 0:
                break
            closing = line.find("-->", opening + 4)
            stop = len(line) if closing < 0 else closing + 3
            for position in range(opening, stop):
                if chars[position] not in {"\r", "\n"}:
                    chars[position] = " "
            if closing < 0:
                comment_start = index
                break
            cursor = stop
        masked_lines.append("".join(chars))

    unclosed_opaque = [(opaque[2], opaque[0])] if opaque is not None else []
    masked_text = "".join(masked_lines)
    return (
        masked_text,
        masked_lines,
        excluded_lines,
        comment_start,
        unclosed_opaque,
    )


def analyze_markdown(
    document: SourceDocument, dialect: str = "commonmark"
) -> tuple[list[Heading], set[int], list[Marker], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    lexical_code = set(document.lexical_code_lines)
    unclosed_line = document.unclosed_fence_line
    unclosed_opaque = document.unclosed_opaque_blocks
    code_lines = set(lexical_code)
    if unclosed_line is not None:
        diagnostics.append(
            diagnostic(
                "unclosed_fence",
                "warning",
                "an unclosed code fence makes the remaining lines non-structural candidates",
                line=unclosed_line + 1,
            )
        )
    if document.unclosed_comment_line is not None:
        diagnostics.append(
            diagnostic(
                "unclosed_html_comment",
                "warning",
                "an unclosed HTML comment makes the remaining lines non-structural candidates",
                line=document.unclosed_comment_line + 1,
            )
        )
    for line, kind in unclosed_opaque:
        diagnostics.append(
            diagnostic(
                "unclosed_opaque_block",
                "warning",
                f"an unclosed {kind} block makes the remaining lines non-structural candidates",
                line=line + 1,
            )
        )

    headings: list[Heading] = []
    try:
        parser = MarkdownIt("commonmark", {"html": False})
        if dialect == "gfm":
            parser.enable("table")
        tokens = parser.parse(document.masked_text)
        for index, token in enumerate(tokens):
            if token.type in {"fence", "code_block"} and token.map:
                code_lines |= line_set(token.map[0], token.map[1])
            if token.type == "heading_open" and token.map:
                start, end = token.map
                if start in document.excluded_lines or start in code_lines:
                    continue
                level = int(token.tag[1])
                content = ""
                if index + 1 < len(tokens) and tokens[index + 1].type == "inline":
                    content = tokens[index + 1].content.strip()
                headings.append(Heading(start, end, level, content, "ast"))
    except (
        Exception
    ) as exc:  # markdown-it should be total, but recovery must remain available.
        diagnostics.append(
            diagnostic(
                "parser_failed", "warning", f"Markdown token parsing failed: {exc}"
            )
        )

    known_starts = {heading.start for heading in headings}
    for index, raw_line in enumerate(document.masked_lines):
        if (
            index in known_starts
            or index in code_lines
            or index in document.excluded_lines
        ):
            continue
        line = raw_line.rstrip("\r\n")
        match = ATX_HEADING_RE.match(line)
        if match:
            headings.append(
                Heading(
                    index,
                    index + 1,
                    len(match.group(1)),
                    match.group(2).strip(),
                    "scan",
                )
            )
            diagnostics.append(
                diagnostic(
                    "fallback_scan_used",
                    "warning",
                    "source scan recovered a heading",
                    line=index + 1,
                )
            )
            continue
        if index + 1 < len(document.lines) and index + 1 not in code_lines:
            underline = SETEXT_RE.match(document.masked_lines[index + 1].rstrip("\r\n"))
            if underline and line.strip():
                headings.append(
                    Heading(
                        index,
                        index + 2,
                        1 if underline.group(1).startswith("=") else 2,
                        line.strip(),
                        "scan",
                    )
                )
                diagnostics.append(
                    diagnostic(
                        "fallback_scan_used",
                        "warning",
                        "source scan recovered a Setext heading",
                        line=index + 1,
                    )
                )

    headings.sort(key=lambda item: (item.start, item.level))
    markers: list[Marker] = []
    for comment in re.finditer(r"<!--.*?-->", document.text, re.DOTALL):
        marker_match = MARKER_RE.fullmatch(comment.group(0).strip())
        if marker_match is None:
            continue
        start_line = document.text.count("\n", 0, comment.start())
        end_line = document.text.count("\n", 0, comment.end())
        if (
            start_line != end_line
            or start_line in code_lines
            or start_line in document.excluded_lines
            or document.masked_lines[start_line].strip()
        ):
            continue
        key = next(
            value for value in marker_match.groups() if value is not None
        ).strip()
        markers.append(Marker(start_line, key))
    return headings, code_lines, markers, diagnostics


def analyze_tables(
    document: SourceDocument,
    headings: list[Heading],
) -> tuple[list[MarkdownTable], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    tables: list[MarkdownTable] = []
    try:
        tokens = (
            MarkdownIt("commonmark", {"html": False})
            .enable("table")
            .parse(document.masked_text)
        )
    except Exception as exc:
        return [], [
            diagnostic(
                "parser_failed", "warning", f"Markdown table parsing failed: {exc}"
            )
        ]

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type != "table_open" or not token.map:
            index += 1
            continue
        table_start, table_end = token.map
        cursor = index + 1
        headers: list[str] = []
        raw_rows: list[tuple[int, int, list[str]]] = []
        while cursor < len(tokens) and tokens[cursor].type != "table_close":
            row_token = tokens[cursor]
            if row_token.type != "tr_open" or not row_token.map:
                cursor += 1
                continue
            row_start, row_end = row_token.map
            cells: list[str] = []
            header_row = False
            cursor += 1
            while cursor < len(tokens) and tokens[cursor].type != "tr_close":
                current = tokens[cursor]
                if current.type == "th_open":
                    header_row = True
                if current.type == "inline":
                    cells.append(current.content.strip())
                cursor += 1
            if header_row:
                headers = cells
            else:
                raw_rows.append((row_start, row_end, cells))
            cursor += 1

        if not headers:
            diagnostics.append(
                diagnostic(
                    "table_header_missing",
                    "warning",
                    "a GFM table has no recoverable header",
                    line=table_start + 1,
                )
            )
            index = cursor + 1
            continue
        if len(set(headers)) != len(headers):
            diagnostics.append(
                diagnostic(
                    "table_header_duplicate",
                    "warning",
                    "a GFM table has duplicate column names",
                    line=table_start + 1,
                    details={"columns": headers},
                )
            )
        rows: list[TableRow] = []
        for row_start, row_end, values in raw_rows:
            if row_end - row_start != 1:
                diagnostics.append(
                    diagnostic(
                        "table_row_multiline",
                        "warning",
                        "a table row spans multiple physical lines and is not a stable record",
                        line=row_start + 1,
                    )
                )
                continue
            if len(values) != len(headers):
                diagnostics.append(
                    diagnostic(
                        "table_row_width_mismatch",
                        "warning",
                        "a table row does not match the declared header width",
                        line=row_start + 1,
                        details={"expected": len(headers), "actual": len(values)},
                    )
                )
                continue
            rows.append(
                TableRow(
                    start=row_start,
                    end=row_end,
                    values=values,
                    cells=dict(zip(headers, values, strict=True)),
                )
            )
        preceding = [heading for heading in headings if heading.start < table_start]
        tables.append(
            MarkdownTable(
                start=table_start,
                end=table_end,
                header_line=table_start,
                headers=headers,
                rows=rows,
                under_heading=preceding[-1].text if preceding else None,
            )
        )
        index = cursor + 1
    return tables, diagnostics


def table_key_candidates(table: MarkdownTable) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for position, header in enumerate(table.headers):
        ids: list[str] = []
        for row in table.rows:
            value = row.values[position].strip()
            match = re.match(rf"^(?P<id>{GENERIC_ID_PATTERN})(?:\s+.*)?$", value)
            if match is not None:
                ids.append(match.group("id"))
        if len(ids) >= 2 and len(ids) == len(table.rows) and len(set(ids)) == len(ids):
            candidates.append(
                {
                    "column": header,
                    "pattern": rf"^(?P<id>{GENERIC_ID_PATTERN})(?:\s+.*)?$",
                    "group": "id",
                    "count": len(ids),
                    "unique": True,
                    "samples": ids[:3],
                }
            )
    return candidates


def table_profile(
    table: MarkdownTable, key_candidate: dict[str, Any]
) -> dict[str, Any]:
    key_column = key_candidate["column"]
    fields: dict[str, Any] = {}
    used: set[str] = set()
    for position, header in enumerate(table.headers):
        if header == key_column:
            name = "title"
            spec: dict[str, Any] = {
                "source": "column",
                "column": header,
                "pattern": rf"^(?:{GENERIC_ID_PATTERN})(?:\s+(?P<title>.*))?$",
                "group": "title",
            }
        else:
            name = field_name_from_header(header, position)
            base = name
            suffix = 2
            while name in used or name == "title":
                name = f"{base}_{suffix}"
                suffix += 1
            spec = {"source": "column", "column": header}
        used.add(name)
        fields[name] = spec
    selected = list(fields)[: min(6, len(fields))]
    boundary: dict[str, Any] = {
        "source": "table-row",
        "columns": table.headers,
    }
    if table.under_heading:
        boundary["under_heading"] = table.under_heading
    return {
        "version": 2,
        "dialect": "gfm",
        "records": {
            "boundary": boundary,
            "key": {
                "source": "column",
                "column": key_column,
                "pattern": key_candidate["pattern"],
                "group": key_candidate["group"],
            },
        },
        "fields": fields,
        "queries": {
            "by_id": {
                "when": {"pattern": rf"^{GENERIC_ID_PATTERN}$"},
                "match": {"source": "key", "operator": "eq"},
                "select": selected,
                "expect": {
                    "max_record_lines": 1,
                    "max_record_bytes": 16384,
                    "structured": True,
                },
            }
        },
        "maintenance": {
            "query_contract": {
                "mode": "propose",
                "allow": ["queries", "fields", "records"],
                "max_changes_per_run": 1,
            }
        },
        "tolerance": {"incomplete": True},
    }


def regex_value(pattern: str | None, text: str, group: str | int | None) -> str | None:
    if pattern is None:
        return text.strip()
    if len(text) > MAX_REGEX_LINE:
        text = text[:MAX_REGEX_LINE]
    match = compile_profile_pattern(pattern).search(text, timeout=REGEX_TIMEOUT_SECONDS)
    return match_group(match, group) if match else None


@lru_cache(maxsize=128)
def compile_profile_pattern(pattern: str) -> profile_regex.Pattern[str]:
    return profile_regex.compile(pattern, profile_regex.VERSION0)


def strip_label_prefix(line: str) -> str:
    value = line.strip()
    value = re.sub(r"^(?:>[ \t]*)+", "", value)
    value = re.sub(r"^[-*+][ \t]+", "", value)
    return value.strip()


def label_occurrences(
    document: SourceDocument,
    start: int,
    end: int,
    labels: Iterable[str],
    code_lines: set[int],
) -> list[dict[str, Any]]:
    wanted = {normalize_label(label) for label in labels}
    found: list[dict[str, Any]] = []
    for index in range(start, min(end, len(document.lines))):
        if index in code_lines or index in document.excluded_lines:
            continue
        line = document.masked_lines[index].rstrip("\r\n")
        stripped = strip_label_prefix(line)
        if stripped.startswith("|") and stripped.count("|") >= 2:
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 2 and normalize_label(cells[0]) in wanted:
                found.append({"value": cells[1].strip(), "line": index + 1})
                continue
        match = re.match(
            r"^(?P<label>(?:\*\*|__|`)?[^:：|]+?(?:\*\*|__|`)?)[ \t]*[:：][ \t]*(?P<value>.*)$",
            stripped,
        )
        if match and normalize_label(match.group("label")) in wanted:
            found.append({"value": match.group("value").strip(), "line": index + 1})
    return found


def resolve_scalar(
    field_name: str,
    values: list[dict[str, Any]],
    record_diagnostics: list[dict[str, Any]],
) -> Any:
    non_empty = [item for item in values if item.get("value") not in {None, ""}]
    distinct: dict[str, list[int]] = {}
    originals: dict[str, Any] = {}
    for item in non_empty:
        key = str(item["value"])
        distinct.setdefault(key, []).append(item.get("line"))
        originals[key] = item["value"]
    if not distinct:
        record_diagnostics.append(
            diagnostic(
                "missing_field", "info", f"field {field_name} is absent or incomplete"
            )
        )
        return None
    if len(distinct) > 1:
        record_diagnostics.append(
            diagnostic(
                "field_conflict",
                "warning",
                f"field {field_name} has conflicting values",
                details={
                    "field": field_name,
                    "values": [
                        {"value": originals[k], "lines": v} for k, v in distinct.items()
                    ],
                },
            )
        )
        return None
    return originals[next(iter(distinct))]


def key_from_heading(heading: Heading | None, spec: dict[str, Any]) -> str | None:
    if heading is None:
        return None
    return regex_value(spec.get("pattern"), heading.text, spec.get("group"))


def heading_is_boundary(
    heading: Heading, boundary: dict[str, Any], has_marker: bool
) -> tuple[bool, float]:
    levels: list[int] = boundary["levels"]
    expected = heading.level in levels
    distance = min(abs(heading.level - level) for level in levels)
    within = expected or distance <= boundary.get("level_tolerance", 0)
    if not within:
        return False, 0.0
    pattern_ok = regex_value(boundary.get("pattern"), heading.text, None) is not None
    if boundary.get("pattern") and not pattern_ok and not has_marker:
        return False, 0.0
    if not expected and not has_marker:
        return True, 0.8
    return (
        True,
        1.0
        if heading.source == "ast" and expected
        else 0.6
        if heading.source == "scan"
        else 0.8,
    )


def nearest_marker(markers: list[Marker], heading: Heading) -> Marker | None:
    candidates = [marker for marker in markers if 0 <= heading.start - marker.line <= 3]
    if not candidates:
        return None
    marker = max(candidates, key=lambda item: item.line)
    return marker


@dataclass
class BoundaryCandidate:
    start: int
    heading: Heading | None
    marker: Marker | None
    confidence: float
    diagnostics: list[dict[str, Any]]
    table_row: TableRow | None = None
    fixed_end: int | None = None


def collect_boundaries(
    document: SourceDocument,
    profile: dict[str, Any],
    headings: list[Heading],
    code_lines: set[int],
    markers: list[Marker],
    tables: list[MarkdownTable],
) -> list[BoundaryCandidate]:
    boundary_spec = profile["records"]["boundary"]
    key_spec = profile["records"]["key"]
    candidates: list[BoundaryCandidate] = []
    used_markers: set[int] = set()

    if boundary_spec.get("source") == "table-row":
        declared_columns = boundary_spec["columns"]
        wanted_heading = boundary_spec.get("under_heading")
        matching_tables = [
            table
            for table in tables
            if table.headers == declared_columns
            and (wanted_heading is None or table.under_heading == wanted_heading)
            and len(set(table.headers)) == len(table.headers)
        ]
        if len(matching_tables) > 1:
            return []
        if matching_tables:
            for row in matching_tables[0].rows:
                candidates.append(
                    BoundaryCandidate(
                        start=row.start,
                        heading=None,
                        marker=None,
                        confidence=1.0,
                        diagnostics=[],
                        table_row=row,
                        fixed_end=row.end - 1,
                    )
                )
    else:
        for heading in headings:
            marker = nearest_marker(markers, heading)
            accepted, confidence = heading_is_boundary(
                heading, boundary_spec, marker is not None
            )
            if not accepted:
                continue
            if heading.level not in boundary_spec["levels"] and marker is None:
                # Heading drift needs identity evidence, not level proximity alone.
                evidence: str | None = None
                if key_spec.get("source") == "heading":
                    evidence = key_from_heading(heading, key_spec)
                elif key_spec.get("source") == "label":
                    provisional_end = len(document.lines)
                    for later in headings:
                        if later.start > heading.start and later.level <= heading.level:
                            provisional_end = later.start
                            break
                    values = label_occurrences(
                        document,
                        heading.end,
                        provisional_end,
                        key_spec["labels"],
                        code_lines,
                    )
                    values = apply_value_pattern(values, key_spec)
                    distinct = {
                        str(item["value"]).strip()
                        for item in values
                        if item.get("value")
                    }
                    evidence = next(iter(distinct)) if len(distinct) == 1 else None
                if evidence is None:
                    continue
            item_diagnostics: list[dict[str, Any]] = []
            if heading.level not in boundary_spec["levels"]:
                item_diagnostics.append(
                    diagnostic(
                        "heading_level_drift",
                        "warning",
                        f"record heading level {heading.level} differs from declared levels",
                        line=heading.start + 1,
                    )
                )
            start = marker.line if marker is not None else heading.start
            if marker is not None:
                used_markers.add(marker.line)
            candidates.append(
                BoundaryCandidate(start, heading, marker, confidence, item_diagnostics)
            )

    for marker in markers:
        if marker.line in used_markers:
            continue
        candidates.append(
            BoundaryCandidate(
                marker.line,
                None,
                marker,
                0.8,
                [
                    diagnostic(
                        "marker_fallback",
                        "warning",
                        "record identity and boundary recovered from an explicit marker",
                        line=marker.line + 1,
                    )
                ],
            )
        )

    candidates.sort(key=lambda item: item.start)
    deduplicated: list[BoundaryCandidate] = []
    for candidate in candidates:
        if deduplicated and candidate.start == deduplicated[-1].start:
            existing = deduplicated[-1]
            if existing.heading is None and candidate.heading is not None:
                existing.heading = candidate.heading
            if existing.marker is None and candidate.marker is not None:
                existing.marker = candidate.marker
            existing.confidence = max(existing.confidence, candidate.confidence)
            existing.diagnostics.extend(candidate.diagnostics)
        else:
            deduplicated.append(candidate)
    return deduplicated


def section_values(
    document: SourceDocument,
    record_start: int,
    record_end: int,
    headings: list[Heading],
    names: list[str],
) -> list[dict[str, Any]]:
    wanted = {normalize_label(name) for name in names}
    inside = [
        heading for heading in headings if record_start < heading.start <= record_end
    ]
    values: list[dict[str, Any]] = []
    for position, heading in enumerate(inside):
        if normalize_label(heading.text) not in wanted:
            continue
        content_start = heading.end
        content_end = record_end + 1
        for later in inside[position + 1 :]:
            if later.level <= heading.level:
                content_end = min(content_end, later.start)
                break
        value = "".join(document.lines[content_start:content_end]).strip()
        values.append({"value": value, "line": heading.start + 1})
    return values


def regex_field_values(
    document: SourceDocument,
    start: int,
    end: int,
    spec: dict[str, Any],
    code_lines: set[int],
) -> list[dict[str, Any]]:
    pattern = spec["pattern"]
    group = spec.get("group")
    values: list[dict[str, Any]] = []
    for index in range(start, min(end, len(document.lines))):
        if index in code_lines or index in document.excluded_lines:
            continue
        line = document.masked_lines[index].rstrip("\r\n")[:MAX_REGEX_LINE]
        match = compile_profile_pattern(pattern).search(
            line, timeout=REGEX_TIMEOUT_SECONDS
        )
        if match:
            value = match_group(match, group)
            values.append({"value": value, "line": index + 1})
    return values


def apply_value_pattern(
    values: list[dict[str, Any]], spec: dict[str, Any]
) -> list[dict[str, Any]]:
    if "pattern" not in spec:
        return values
    transformed: list[dict[str, Any]] = []
    for item in values:
        value = regex_value(spec["pattern"], str(item["value"]), spec.get("group"))
        if value is not None:
            transformed.append({"value": value, "line": item.get("line")})
    return transformed


def extract_fields(
    document: SourceDocument,
    profile: dict[str, Any],
    record: Record,
    headings: list[Heading],
    code_lines: set[int],
) -> None:
    key_spec = profile["records"]["key"]
    body_start = record.start
    if record.marker is not None and body_start == record.marker.line:
        body_start = record.marker.line + 1
    if record.heading is not None:
        body_start = max(body_start, record.heading.end)

    for name, spec in profile.get("fields", {}).items():
        source = spec["source"]
        values: list[dict[str, Any]] = []
        if source == "heading":
            if record.heading is not None:
                pattern = spec.get("pattern", key_spec.get("pattern"))
                value = regex_value(pattern, record.heading.text, spec.get("group"))
                if value is not None:
                    values.append({"value": value, "line": record.heading.start + 1})
        elif source == "label":
            values = label_occurrences(
                document, body_start, record.end + 1, spec["labels"], code_lines
            )
            values = apply_value_pattern(values, spec)
        elif source == "section":
            values = section_values(
                document, body_start, record.end, headings, spec["headings"]
            )
        elif source == "body":
            value = "".join(document.lines[body_start : record.end + 1]).strip()
            if value:
                values.append({"value": value, "line": body_start + 1})
        elif source == "regex":
            values = regex_field_values(
                document, body_start, record.end + 1, spec, code_lines
            )
        elif source == "column" and record.table_row is not None:
            value = record.table_row.cells.get(spec["column"])
            if value is not None:
                extracted = regex_value(spec.get("pattern"), value, spec.get("group"))
                if extracted is not None:
                    values.append(
                        {"value": extracted, "line": record.table_row.start + 1}
                    )
        record.fields[name] = resolve_scalar(name, values, record.diagnostics)


def declared_key(
    document: SourceDocument,
    profile: dict[str, Any],
    start: int,
    end: int,
    heading: Heading | None,
    marker: Marker | None,
    table_row: TableRow | None,
    code_lines: set[int],
) -> tuple[str | None, dict[str, Any] | None]:
    spec = profile["records"]["key"]
    source = spec["source"]
    if source == "heading":
        value = key_from_heading(heading, spec)
        return value, (
            {"source": "heading", "value": value, "line": heading.start + 1}
            if value
            else None
        )
    if source == "marker":
        value = marker.key.strip() if marker else None
        return value, (
            {"source": "marker", "value": value, "line": marker.line + 1}
            if value
            else None
        )
    if source == "column":
        raw = table_row.cells.get(spec["column"]) if table_row is not None else None
        value = (
            regex_value(spec.get("pattern"), raw, spec.get("group"))
            if raw is not None
            else None
        )
        return value, (
            {
                "source": "column",
                "column": spec["column"],
                "value": value,
                "line": table_row.start + 1,
            }
            if value is not None and table_row is not None
            else None
        )
    occurrences = label_occurrences(
        document, start, end + 1, spec["labels"], code_lines
    )
    occurrences = apply_value_pattern(occurrences, spec)
    unique = {
        str(item["value"]).strip()
        for item in occurrences
        if item.get("value") not in {None, ""}
    }
    if len(unique) == 1:
        value = next(iter(unique))
        first = next(
            item for item in occurrences if str(item["value"]).strip() == value
        )
        return value, {"source": "label", "value": value, "line": first["line"]}
    return None, (
        {"source": "label-conflict", "values": occurrences} if occurrences else None
    )


def build_records(
    document: SourceDocument,
    profile: dict[str, Any],
    headings: list[Heading],
    code_lines: set[int],
    markers: list[Marker],
    tables: list[MarkdownTable],
) -> tuple[list[Record], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    boundaries = collect_boundaries(
        document, profile, headings, code_lines, markers, tables
    )
    records: list[Record] = []
    allow_incomplete = profile.get("tolerance", {}).get("incomplete", False)

    if not boundaries:
        diagnostics.append(
            diagnostic(
                "no_records",
                "warning",
                "no record boundaries matched the current profile",
            )
        )

    for position, boundary in enumerate(boundaries):
        end = boundary.fixed_end
        if end is None:
            end = (
                boundaries[position + 1].start - 1
                if position + 1 < len(boundaries)
                else len(document.lines) - 1
            )
        item_diagnostics = list(boundary.diagnostics)
        value, evidence = declared_key(
            document,
            profile,
            boundary.start,
            end,
            boundary.heading,
            boundary.marker,
            boundary.table_row,
            code_lines,
        )
        identity_evidence: list[dict[str, Any]] = []
        key_conflict = bool(evidence and evidence.get("source") == "label-conflict")
        if evidence:
            if key_conflict:
                identity_evidence.extend(
                    {
                        "source": "label",
                        "value": item.get("value"),
                        "line": item.get("line"),
                    }
                    for item in evidence.get("values", [])
                )
                item_diagnostics.append(
                    diagnostic(
                        "key_conflict",
                        "warning",
                        "declared key labels contain conflicting values; record is candidate-only",
                        line=boundary.start + 1,
                        details={"evidence": identity_evidence},
                    )
                )
            else:
                identity_evidence.append(evidence)
        marker_value = boundary.marker.key.strip() if boundary.marker else None
        if marker_value and not any(
            item.get("source") == "marker" and item.get("value") == marker_value
            for item in identity_evidence
        ):
            identity_evidence.append(
                {
                    "source": "marker",
                    "value": marker_value,
                    "line": boundary.marker.line + 1,
                }
            )

        declared_values: set[str] = set()
        if value:
            declared_values.add(value)
        if marker_value:
            declared_values.add(marker_value)
        if key_conflict:
            value = None
            confidence = min(boundary.confidence, 0.4)
        elif len(declared_values) > 1:
            item_diagnostics.append(
                diagnostic(
                    "marker_conflict",
                    "warning",
                    "marker and declared key evidence disagree; record is a candidate only",
                    line=boundary.start + 1,
                    details={"evidence": identity_evidence},
                )
            )
            value = None
            confidence = min(boundary.confidence, 0.4)
        elif value is None and marker_value:
            value = marker_value
            confidence = min(boundary.confidence, 0.8)
        else:
            confidence = boundary.confidence

        if value is None:
            item_diagnostics.append(
                diagnostic(
                    "missing_key",
                    "warning",
                    "record has no recoverable key",
                    line=boundary.start + 1,
                )
            )
        if (
            not allow_incomplete
            and value is not None
            and boundary.heading is None
            and boundary.table_row is None
        ):
            item_diagnostics.append(
                diagnostic(
                    "incomplete_record",
                    "warning",
                    "marker-only record is candidate-only because tolerance.incomplete is false",
                    line=boundary.start + 1,
                )
            )
            confidence = min(confidence, 0.4)

        record = Record(
            key=value,
            start=boundary.start,
            end=max(boundary.start, end),
            heading=boundary.heading,
            marker=boundary.marker,
            table_row=boundary.table_row,
            fields={},
            confidence=confidence,
            diagnostics=item_diagnostics,
            identity_evidence=identity_evidence,
        )
        extract_fields(document, profile, record, headings, code_lines)
        records.append(record)

    by_key: dict[str, list[Record]] = {}
    for record in records:
        if record.key is not None and record.confidence >= 0.6:
            by_key.setdefault(record.key, []).append(record)
    for key, matches in by_key.items():
        if len(matches) > 1:
            locations = [
                {"line": item.start + 1, "confidence": item.confidence}
                for item in matches
            ]
            diagnostics.append(
                diagnostic(
                    "duplicate_key",
                    "warning",
                    f"key {key!r} identifies {len(matches)} records",
                    details={"key": key, "locations": locations},
                )
            )
    for record in records:
        diagnostics.extend(record.diagnostics)
    return records, diagnostics


def serialize_record(document: SourceDocument, record: Record) -> dict[str, Any]:
    line_start = record.start + 1
    line_end = record.end + 1
    byte_start = document.byte_offsets[
        min(record.start, len(document.byte_offsets) - 1)
    ]
    byte_end_index = min(record.end + 1, len(document.byte_offsets) - 1)
    payload: dict[str, Any] = {
        "key": record.key,
        "fields": record.fields,
        "line_start": line_start,
        "line_end": line_end,
        "byte_start": byte_start,
        "byte_end": document.byte_offsets[byte_end_index],
        "confidence": round(record.confidence, 2),
        "diagnostics": record.diagnostics,
    }
    if record.identity_evidence:
        payload["identity_evidence"] = record.identity_evidence
    return payload


def extract_current(
    document: SourceDocument,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if document.profile is None:
        return [], list(document.diagnostics)
    headings, code_lines, markers, parse_diagnostics = analyze_markdown(
        document, document.profile.get("dialect", "commonmark")
    )
    tables, table_diagnostics = analyze_tables(document, headings)
    records, record_diagnostics = build_records(
        document, document.profile, headings, code_lines, markers, tables
    )
    serialized = [serialize_record(document, record) for record in records]
    return serialized, list(
        document.diagnostics
    ) + parse_diagnostics + table_diagnostics + record_diagnostics


def index_path(document: SourceDocument) -> tuple[Path | None, dict[str, Any] | None]:
    if document.profile is None or "index" not in document.profile:
        return None, diagnostic(
            "index_missing", "info", "profile does not declare an index path"
        )
    configured = Path(document.profile["index"])
    if configured.is_absolute():
        return None, diagnostic(
            "index_unsafe", "error", "index path must be relative to the document"
        )
    base = document.path.parent.resolve()
    unresolved = base / configured
    if unresolved.is_symlink():
        return None, diagnostic(
            "index_unsafe", "error", "index path must not be a symlink"
        )
    if unresolved.exists() and not unresolved.is_file():
        return None, diagnostic(
            "index_unsafe", "error", "index path must name a regular file"
        )
    candidate = unresolved.resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError:
        return None, diagnostic(
            "index_unsafe", "error", "index path escapes the document directory"
        )
    same_as_source = candidate == document.path
    if candidate.exists() and not same_as_source:
        try:
            same_as_source = candidate.samefile(document.path)
        except OSError:
            same_as_source = False
    if same_as_source:
        return None, diagnostic(
            "index_unsafe", "error", "index path must not overwrite the source"
        )
    return candidate, None


def load_valid_index(
    document: SourceDocument,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    path, problem = index_path(document)
    if problem:
        return None, [problem]
    assert path is not None
    if not path.exists():
        return None, [
            diagnostic("index_missing", "info", f"index does not exist: {path}")
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            diagnostic("index_invalid", "warning", f"index could not be read: {exc}")
        ]
    if not isinstance(payload, dict):
        return None, [
            diagnostic("index_invalid", "warning", "index root must be an object")
        ]
    expected = {
        "index_schema": INDEX_SCHEMA,
        "engine": ENGINE,
        "protocol_version": document.profile["version"],
        "source": str(document.path),
        "source_sha256": document.source_hash,
        "profile_sha256": document.profile_hash,
    }
    mismatches = {
        key: {"expected": value, "actual": payload.get(key)}
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        code = (
            "index_stale"
            if {"source_sha256", "profile_sha256"} & set(mismatches)
            else "index_invalid"
        )
        return None, [
            diagnostic(
                code,
                "warning",
                "index metadata does not match the current document; current source will be parsed",
                details=mismatches,
            )
        ]
    records = payload.get("records")
    if not isinstance(records, list):
        return None, [
            diagnostic("index_invalid", "warning", "index records must be an array")
        ]
    return records, []


def records_for_query(
    document: SourceDocument,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if document.profile is None:
        return [], list(document.diagnostics)
    if (document.profile_source or "").startswith(TEMPORARY_PROFILE_PREFIX):
        records, diagnostics = extract_current(document)
        confidence_cap = 0.9 if document.profile_source.endswith("explicit") else 0.8
        for item in records:
            item["confidence"] = min(confidence_cap, float(item.get("confidence", 0.0)))
        return records, diagnostics
    cached, index_diagnostics = load_valid_index(document)
    records, diagnostics = extract_current(document)
    if cached is not None:
        if normalized_json(cached) == normalized_json(records):
            index_diagnostics.append(
                diagnostic(
                    "index_verified", "info", "index matched a fresh source extraction"
                )
            )
        else:
            index_diagnostics.append(
                diagnostic(
                    "index_invalid",
                    "warning",
                    "index records differ from current source extraction and were ignored",
                )
            )
    return records, diagnostics + index_diagnostics


def status_for(records: list[dict[str, Any]], *, invalid: bool = False) -> str:
    if invalid:
        return "invalid"
    if not records:
        return "not_found"
    return "matched" if len(records) == 1 else "ambiguous"


def error_diagnostics(items: list[dict[str, Any]]) -> bool:
    return any(item.get("severity") == "error" for item in items)


def temporary_selector_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "record_levels": list(getattr(args, "record_level", None) or []),
        "key_labels": list(getattr(args, "key_label", None) or []),
        "key_pattern": getattr(args, "key_pattern", None),
        "key_group": getattr(args, "key_group", None),
    }


def has_temporary_selector_arguments(args: argparse.Namespace) -> bool:
    return any(temporary_selector_arguments(args).values())


def visible_label_items(
    document: SourceDocument, code_lines: set[int]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, raw_line in enumerate(document.masked_lines):
        if index in code_lines or index in document.excluded_lines:
            continue
        stripped = strip_label_prefix(raw_line.rstrip("\r\n"))
        if stripped.startswith("|") and stripped.count("|") >= 2:
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 2 and cells[0]:
                items.append({"label": cells[0], "value": cells[1], "line": index})
            continue
        match = re.match(
            r"^(?P<label>(?:\*\*|__|`)?[^:：|]+?(?:\*\*|__|`)?)"
            r"[ \t]*[:：][ \t]*(?P<value>.*)$",
            stripped,
        )
        if match:
            label = re.sub(r"[*_`]", "", match.group("label")).strip()
            if label:
                items.append(
                    {
                        "label": label,
                        "value": match.group("value").strip(),
                        "line": index,
                    }
                )
    return items


def nearest_heading_level(headings: list[Heading], line: int) -> int | None:
    preceding = [heading for heading in headings if heading.start < line]
    return preceding[-1].level if preceding else None


def inferred_section_levels(headings: list[Heading]) -> list[int]:
    if not headings:
        return []
    counts = Counter(heading.level for heading in headings)
    repeated = [level for level, count in counts.items() if count > 1]
    if repeated:
        return [min(repeated)]
    # A single H1 followed by a single H2 is usually a document title plus one record.
    return [max(counts)]


def inferred_generic_id_level(items: list[tuple[Heading, str]]) -> int | None:
    if not items:
        return None
    # Prefer the shallowest evidence so nested examples cannot outvote their record.
    return min(heading.level for heading, _key in items)


def temporary_profile_fields() -> dict[str, Any]:
    return {
        "title": {
            "source": "heading",
            "pattern": r"^(?P<value>.*)$",
            "group": "value",
        },
        "body": {"source": "body"},
    }


def prepare_temporary_profile(
    document: SourceDocument,
    args: argparse.Namespace,
    *,
    requested: str | None,
) -> list[dict[str, Any]]:
    """Attach an in-memory-only profile when the source has no valid profile."""
    if document.profile is not None:
        if has_temporary_selector_arguments(args):
            document.diagnostics.append(
                diagnostic(
                    "temporary_selectors_ignored",
                    "info",
                    "temporary selectors were ignored because the document declares an mdq profile",
                )
            )
        return []
    if error_diagnostics(document.diagnostics):
        # A conflicting or invalid declared profile must not silently become an ad hoc query.
        return []

    headings, code_lines, _markers, parse_diagnostics = analyze_markdown(document)
    labels = visible_label_items(document, code_lines)
    supplied = temporary_selector_arguments(args)
    explicit = has_temporary_selector_arguments(args)

    levels = sorted(set(supplied["record_levels"]))
    key_labels = list(dict.fromkeys(supplied["key_labels"]))
    key_pattern = supplied["key_pattern"]
    key_group = supplied["key_group"]
    key_source = "label" if key_labels else "heading"

    if explicit:
        selector_diagnostics: list[dict[str, Any]] = []
        compiled = (
            safe_compile(key_pattern, "temporary key pattern", selector_diagnostics)
            if key_pattern is not None
            else None
        )
        if key_group is not None and key_pattern is None:
            selector_diagnostics.append(
                diagnostic(
                    "profile_invalid",
                    "error",
                    "temporary key group requires --key-pattern",
                )
            )
        elif key_group is not None:
            validate_group(
                compiled, key_group, "temporary key group", selector_diagnostics
            )
        if any(not label.strip() for label in key_labels):
            selector_diagnostics.append(
                diagnostic(
                    "profile_invalid",
                    "error",
                    "temporary key labels must not be empty",
                )
            )
        if error_diagnostics(selector_diagnostics):
            document.diagnostics.extend(selector_diagnostics)
            return parse_diagnostics

    generic_headings: list[tuple[Heading, str]] = []
    for heading in headings:
        key = regex_value(TEMPORARY_GENERIC_KEY_PATTERN, heading.text, "id")
        if key:
            generic_headings.append((heading, key))
    generic_level = inferred_generic_id_level(generic_headings)
    canonical_generic_headings = [
        item for item in generic_headings if item[0].level == generic_level
    ]

    if not explicit and requested is not None:
        exact_generic_headings = [
            heading for heading, key in canonical_generic_headings if key == requested
        ]
        exact_heading_text = [
            heading for heading in headings if heading.text.strip() == requested
        ]
        exact_labels = [
            item
            for item in labels
            if item["value"].strip() == requested
            and normalize_label(item["label"]) in INFERRED_KEY_LABELS
        ]
        if exact_generic_headings:
            assert generic_level is not None
            levels = [generic_level]
            key_pattern = TEMPORARY_GENERIC_KEY_PATTERN
            key_group = "id"
        elif exact_heading_text:
            levels = sorted({heading.level for heading in exact_heading_text})
        elif exact_labels:
            key_source = "label"
            key_labels = list(dict.fromkeys(item["label"] for item in exact_labels))
            levels = sorted(
                {
                    level
                    for item in exact_labels
                    if (level := nearest_heading_level(headings, item["line"]))
                    is not None
                }
            )
        elif canonical_generic_headings:
            # The requested key may simply be absent; preserve exact not-found semantics.
            assert generic_level is not None
            levels = [generic_level]
            key_pattern = TEMPORARY_GENERIC_KEY_PATTERN
            key_group = "id"
        else:
            levels = inferred_section_levels(headings)
    elif not explicit:
        if canonical_generic_headings:
            assert generic_level is not None
            levels = [generic_level]
            key_pattern = TEMPORARY_GENERIC_KEY_PATTERN
            key_group = "id"
        else:
            levels = inferred_section_levels(headings)
    else:
        if key_source == "label" and not levels:
            wanted = {normalize_label(label) for label in key_labels}
            levels = sorted(
                {
                    level
                    for item in labels
                    if normalize_label(item["label"]) in wanted
                    and (level := nearest_heading_level(headings, item["line"]))
                    is not None
                }
            )
        if not levels:
            levels = inferred_section_levels(headings)

    if not levels:
        return parse_diagnostics + [
            diagnostic(
                "temporary_selectors_unavailable",
                "info",
                "no safe record boundary could be inferred; line-local fallback will be used",
            )
        ]

    boundary: dict[str, Any] = {
        "source": "heading",
        "levels": levels,
        "level_tolerance": 0,
    }
    key: dict[str, Any] = {"source": key_source}
    if key_labels:
        key["labels"] = key_labels
    if key_pattern:
        key["pattern"] = key_pattern
    if key_group is not None:
        key["group"] = key_group
    proposed = {
        "version": 1,
        "dialect": "commonmark",
        "records": {"boundary": boundary, "key": key},
        "fields": temporary_profile_fields(),
        "tolerance": {"incomplete": True},
    }
    validation_diagnostics: list[dict[str, Any]] = []
    validated = validate_profile(proposed, validation_diagnostics)
    if validated is None:
        document.diagnostics.extend(validation_diagnostics)
        return parse_diagnostics

    document.profile = validated
    document.profile_source = (
        f"{TEMPORARY_PROFILE_PREFIX}explicit"
        if explicit
        else f"{TEMPORARY_PROFILE_PREFIX}inferred"
    )
    document.diagnostics.append(
        diagnostic(
            "temporary_selectors_applied"
            if explicit
            else "temporary_selectors_inferred",
            "info",
            "an in-memory query profile was applied and was not written to the Markdown file",
            details={
                "source": "explicit" if explicit else "inferred",
                "record_levels": levels,
                "key_source": key_source,
                "key_labels": key_labels,
                "key_pattern": key_pattern,
                "key_group": key_group,
            },
        )
    )
    return []


def visible_record_text(
    document: SourceDocument,
    record: dict[str, Any],
    *,
    include_heading: bool = True,
) -> str:
    start = max(0, int(record.get("line_start", 1)) - 1)
    end = min(len(document.lines), int(record.get("line_end", start + 1)))
    if not include_heading:
        cursor = start
        while cursor < end and (
            cursor in document.excluded_lines
            or not document.masked_lines[cursor].strip()
        ):
            cursor += 1
        if cursor < end and ATX_HEADING_RE.match(
            document.masked_lines[cursor].rstrip("\r\n")
        ):
            start = cursor + 1
        elif (
            cursor + 1 < end
            and document.masked_lines[cursor].strip()
            and SETEXT_RE.match(document.masked_lines[cursor + 1].rstrip("\r\n"))
        ):
            start = cursor + 2
    return "".join(
        document.masked_lines[index]
        for index in range(start, end)
        if index not in document.lexical_code_lines
        and index not in document.excluded_lines
    )


def line_local_record(
    document: SourceDocument,
    line: int,
    *,
    key: str | None,
    context: str,
    confidence: float,
    evidence_source: str,
    evidence_value: str | None = None,
) -> dict[str, Any]:
    item_diagnostics = [
        diagnostic(
            "line_local_fallback",
            "warning" if confidence < 0.6 else "info",
            "the match is line-local because no safe Markdown record boundary was available",
            line=line + 1,
        )
    ]
    return {
        "key": key,
        "fields": {"context": context},
        "line_start": line + 1,
        "line_end": line + 1,
        "byte_start": document.byte_offsets[line],
        "byte_end": document.byte_offsets[
            min(line + 1, len(document.byte_offsets) - 1)
        ],
        "confidence": confidence,
        "diagnostics": item_diagnostics,
        "identity_evidence": [
            {
                "source": evidence_source,
                "value": key if evidence_value is None else evidence_value,
                "line": line + 1,
            }
        ],
    }


def literal_is_present(text: str, needle: str, *, case_sensitive: bool) -> bool:
    if not needle:
        return False
    haystack = text if case_sensitive else text.casefold()
    wanted = needle if case_sensitive else needle.casefold()
    start = 0
    while True:
        position = haystack.find(wanted, start)
        if position < 0:
            return False
        before = haystack[position - 1] if position > 0 else ""
        after_index = position + len(wanted)
        after = haystack[after_index] if after_index < len(haystack) else ""
        identifier = bool(re.fullmatch(r"[A-Za-z0-9_.-]+", wanted))
        boundary_characters = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
        )
        if "-" in wanted:
            boundary_characters += "-"
        if "." in wanted:
            boundary_characters += "."
        if not identifier or (
            (not before or before not in boundary_characters)
            and (not after or after not in boundary_characters)
        ):
            return True
        start = position + 1


def line_local_query_results(
    document: SourceDocument,
    requested: str,
    *,
    key_labels: list[str] | None = None,
    key_pattern: str | None = None,
    key_group: str | int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _headings, code_lines, _markers, parse_diagnostics = analyze_markdown(document)
    labels = visible_label_items(document, code_lines)
    wanted_labels = (
        {normalize_label(label) for label in key_labels}
        if key_labels
        else INFERRED_KEY_LABELS
    )
    matched_label_lines = {
        item["line"]
        for item in labels
        if normalize_label(item["label"]) in wanted_labels
        and (
            regex_value(key_pattern, item["value"].strip(), key_group)
            if key_pattern
            else item["value"].strip()
        )
        == requested
    }
    records = [
        line_local_record(
            document,
            line,
            key=requested,
            context=document.lines[line].rstrip("\r\n"),
            confidence=0.7,
            evidence_source="label",
            evidence_value=requested,
        )
        for line in sorted(matched_label_lines)
    ]
    candidates: list[dict[str, Any]] = []
    for line, masked in enumerate(document.masked_lines):
        if (
            line in matched_label_lines
            or line in code_lines
            or line in document.excluded_lines
            or not literal_is_present(masked, requested, case_sensitive=False)
        ):
            continue
        candidate = line_local_record(
            document,
            line,
            key=None,
            context=document.lines[line].rstrip("\r\n"),
            confidence=0.4,
            evidence_source="body",
            evidence_value=requested,
        )
        candidate["candidate"] = True
        candidates.append(candidate)
    return records + candidates, parse_diagnostics


def line_local_search_records(
    document: SourceDocument, text: str, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _headings, code_lines, _markers, parse_diagnostics = analyze_markdown(document)
    records: list[dict[str, Any]] = []
    for line, masked in enumerate(document.masked_lines):
        if (
            line in code_lines
            or line in document.excluded_lines
            or text.casefold() not in masked.casefold()
        ):
            continue
        records.append(
            line_local_record(
                document,
                line,
                key=None,
                context=document.lines[line].rstrip("\r\n"),
                confidence=0.6,
                evidence_source="literal",
                evidence_value=text,
            )
        )
        if len(records) >= limit:
            break
    return records, parse_diagnostics


def command_inspect(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    dialect = (
        document.profile.get("dialect", "commonmark")
        if document.profile
        else "commonmark"
    )
    headings, code_lines, markers, parse_diagnostics = analyze_markdown(
        document, dialect
    )
    tables, table_diagnostics = analyze_tables(document, headings)
    level_counts = Counter(str(item.level) for item in headings)
    label_counts: Counter[str] = Counter()
    for index, line in enumerate(document.masked_lines):
        if index in code_lines or index in document.excluded_lines:
            continue
        stripped = strip_label_prefix(line.rstrip("\r\n"))
        match = re.match(r"^(?:\*\*|__|`)?([^:：|]+?)(?:\*\*|__|`)?\s*[:：]", stripped)
        if match:
            label = re.sub(r"[*_`]", "", match.group(1)).strip()
            if 0 < len(label) <= 40:
                label_counts[label] += 1
    id_headings = []
    for item in headings:
        match = GENERIC_ID_RE.search(item.text)
        if match:
            id_headings.append(
                {
                    "id": match.group(1),
                    "line": item.start + 1,
                    "level": item.level,
                    "text": item.text,
                }
            )

    table_summaries: list[dict[str, Any]] = []
    suggested_table: tuple[MarkdownTable, dict[str, Any]] | None = None
    for table in tables:
        key_candidates = table_key_candidates(table)
        table_summaries.append(
            {
                "line_start": table.start + 1,
                "line_end": table.end,
                "under_heading": table.under_heading,
                "columns": table.headers,
                "row_count": len(table.rows),
                "candidate_keys": key_candidates,
            }
        )
        if suggested_table is None and len(key_candidates) == 1:
            suggested_table = (table, key_candidates[0])

    suggestion: dict[str, Any] | None = None
    if suggested_table is not None:
        suggestion = table_profile(*suggested_table)
    elif id_headings:
        preferred_level = Counter(entry["level"] for entry in id_headings).most_common(
            1
        )[0][0]
        suggestion = {
            "version": 1,
            "dialect": dialect,
            "records": {
                "boundary": {
                    "source": "heading",
                    "levels": [preferred_level],
                    "level_tolerance": 0,
                },
                "key": {
                    "source": "heading",
                    "pattern": r"^(?P<id>[A-Za-z][A-Za-z0-9_.]*-[0-9]+)(?:\s*[-:：]\s*|\s+)?(?P<title>.*)$",
                    "group": "id",
                },
            },
            "fields": {"title": {"source": "heading", "group": "title"}},
            "tolerance": {"incomplete": True},
        }
    diagnostics = list(document.diagnostics) + parse_diagnostics + table_diagnostics
    if document.profile is not None and tables:
        records, existing_diagnostics = records_for_query(document)
        structured_count = len(
            [
                item
                for item in records
                if item.get("key") is not None and item.get("confidence", 0) >= 0.6
            ]
        )
        table_identity_count = sum(
            candidate["count"]
            for summary in table_summaries
            for candidate in summary["candidate_keys"]
        )
        if table_identity_count >= max(2, structured_count * 2):
            diagnostics.append(
                diagnostic(
                    "record_granularity_mismatch",
                    "warning",
                    "the current contract exposes far fewer records than stable table-row identities",
                    details={
                        "structured_records": structured_count,
                        "table_row_identities": table_identity_count,
                    },
                )
            )
        diagnostics.extend(existing_diagnostics)
    emit(
        {
            "status": "invalid" if error_diagnostics(diagnostics) else "inspected",
            "document": str(document.path),
            "profile": {
                "present": document.profile is not None,
                "source": document.profile_source,
            },
            "heading_levels": dict(sorted(level_counts.items())),
            "candidate_headings": id_headings[:50],
            "common_labels": [
                {"label": key, "count": value}
                for key, value in label_counts.most_common(30)
            ],
            "tables": table_summaries,
            "markers": [{"key": item.key, "line": item.line + 1} for item in markers],
            "suggested_profile": suggestion,
            "diagnostics": diagnostics,
        }
    )
    return 0


def command_validate(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    if document.profile is None:
        emit(
            {
                "status": "invalid",
                "valid": False,
                "document": str(document.path),
                "record_count": 0,
                "diagnostics": document.diagnostics,
            }
        )
        return 3
    records, diagnostics = extract_current(document)
    if "index" in document.profile:
        _, index_problem = index_path(document)
        if index_problem is not None:
            diagnostics.append(index_problem)
    structured = [
        item
        for item in records
        if item.get("key") is not None and item.get("confidence", 0) >= 0.6
    ]
    valid = not error_diagnostics(diagnostics)
    payload: dict[str, Any] = {
        "status": "validated" if valid else "invalid",
        "valid": valid,
        "document": str(document.path),
        "profile_source": document.profile_source,
        "record_count": len(structured),
        "candidate_count": len(records) - len(structured),
        "diagnostics": diagnostics,
    }
    if args.command == "diagnose":
        payload["records"] = records
    emit(payload)
    return 0 if valid else 3


def command_query(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    requested = args.id.strip()
    preparation_diagnostics = prepare_temporary_profile(
        document, args, requested=requested
    )
    if document.profile is None:
        if error_diagnostics(document.diagnostics):
            emit_query_result(
                {
                    "status": "invalid",
                    "count": 0,
                    "records": [],
                    "candidates": [],
                    "diagnostics": document.diagnostics,
                },
                args.output,
            )
            return 3
        selectors = temporary_selector_arguments(args)
        line_key_labels = selectors["key_labels"] or None
        local, parse_diagnostics = line_local_query_results(
            document,
            requested,
            key_labels=line_key_labels,
            key_pattern=selectors["key_pattern"] if line_key_labels else None,
            key_group=selectors["key_group"] if line_key_labels else None,
        )
        structured = [item for item in local if item.get("key") is not None]
        candidates = [item for item in local if item.get("key") is None]
        diagnostics = (
            list(document.diagnostics) + preparation_diagnostics + parse_diagnostics
        )
        if len(structured) > 1:
            diagnostics.append(
                diagnostic(
                    "ambiguous_match",
                    "warning",
                    f"exact key {requested!r} matched {len(structured)} line-local labels",
                )
            )
        elif not structured:
            diagnostics.append(
                diagnostic(
                    "no_match",
                    "info",
                    f"no exact record key matched {requested!r}; body mentions are candidates only",
                )
            )
        output_status = emit_query_result(
            {
                "status": status_for(structured),
                "count": len(structured),
                "records": structured,
                "candidates": candidates,
                "diagnostics": diagnostics,
            },
            args.output,
        )
        return output_status or 0
    records, diagnostics = records_for_query(document)
    if error_diagnostics(diagnostics):
        emit_query_result(
            {
                "status": "invalid",
                "count": 0,
                "records": [],
                "candidates": [],
                "diagnostics": diagnostics,
            },
            args.output,
        )
        return 3
    temporary = (document.profile_source or "").startswith(TEMPORARY_PROFILE_PREFIX)
    structured = [
        item
        for item in records
        if item.get("key") == requested and float(item.get("confidence", 0)) >= 0.6
    ]
    candidates: list[dict[str, Any]] = []
    for item in records:
        key = item.get("key")
        evidence = item.get("identity_evidence", [])
        case_candidate = (
            isinstance(key, str)
            and key != requested
            and key.casefold() == requested.casefold()
        )
        evidence_candidate = any(
            str(entry.get("value", "")).strip().casefold() == requested.casefold()
            for entry in evidence
        )
        if item not in structured and (case_candidate or evidence_candidate):
            candidate = dict(item)
            candidate["candidate"] = True
            candidates.append(candidate)
        elif (
            temporary
            and item not in structured
            and literal_is_present(
                visible_record_text(document, item),
                requested,
                case_sensitive=False,
            )
        ):
            candidate = dict(item)
            candidate["candidate"] = True
            candidate["confidence"] = min(0.4, float(candidate.get("confidence", 0.0)))
            candidate["identity_evidence"] = list(
                candidate.get("identity_evidence", [])
            )
            candidate["identity_evidence"].append(
                {"source": "body", "value": requested}
            )
            candidate["diagnostics"] = list(candidate.get("diagnostics", []))
            candidate["diagnostics"].append(
                diagnostic(
                    "body_identity_candidate",
                    "warning",
                    "the requested key appears only in record content and is candidate-only",
                )
            )
            candidates.append(candidate)
    if not structured and not temporary:
        headings, _code_lines, _markers, table_parse_diagnostics = analyze_markdown(
            document, "gfm"
        )
        tables, table_diagnostics = analyze_tables(document, headings)
        diagnostics.extend(table_parse_diagnostics + table_diagnostics)
        for table in tables:
            for key_candidate in table_key_candidates(table):
                column = key_candidate["column"]
                for row in table.rows:
                    value = regex_value(
                        key_candidate["pattern"],
                        row.cells[column],
                        key_candidate["group"],
                    )
                    if value == requested:
                        candidates.append(
                            {
                                "key": None,
                                "fields": {column: row.cells[column]},
                                "line_start": row.start + 1,
                                "line_end": row.end,
                                "byte_start": document.byte_offsets[row.start],
                                "byte_end": document.byte_offsets[row.end],
                                "confidence": 0.5,
                                "candidate": True,
                                "identity_evidence": [
                                    {
                                        "source": "table-column",
                                        "column": column,
                                        "value": requested,
                                        "line": row.start + 1,
                                    }
                                ],
                                "diagnostics": [
                                    diagnostic(
                                        "table_identity_candidate",
                                        "warning",
                                        "the requested ID is a unique table-row candidate but the contract does not declare table rows",
                                        line=row.start + 1,
                                    )
                                ],
                            }
                        )
        if candidates:
            diagnostics.append(
                diagnostic(
                    "record_granularity_mismatch",
                    "warning",
                    "the requested identity is nested inside a table covered by a broader record boundary",
                )
            )
    if len(structured) > 1:
        diagnostics.append(
            diagnostic(
                "ambiguous_match",
                "warning",
                f"exact key {requested!r} matched {len(structured)} records",
            )
        )
    elif not structured:
        diagnostics.append(
            diagnostic("no_match", "info", f"no exact record key matched {requested!r}")
        )
    output_status = emit_query_result(
        {
            "status": status_for(structured),
            "count": len(structured),
            "records": structured,
            "candidates": candidates,
            "diagnostics": diagnostics,
        },
        args.output,
    )
    return output_status or 0


def searchable_values(record: dict[str, Any], field_name: str | None) -> list[str]:
    if field_name is None:
        values: list[Any] = [record.get("key")]
        values.extend((record.get("fields") or {}).values())
    elif field_name == "key":
        values = [record.get("key")]
    else:
        values = [(record.get("fields") or {}).get(field_name)]
    return [str(value) for value in values if value is not None]


def query_matches(
    records: list[dict[str, Any]], spec: dict[str, Any], value: str
) -> list[dict[str, Any]]:
    match = spec["match"]
    field_name = "key" if match["source"] == "key" else match["field"]
    operator = match.get("operator", "eq")
    selected: list[dict[str, Any]] = []
    for record in records:
        values = searchable_values(record, field_name)
        if operator == "eq":
            matched = any(item == value for item in values)
        else:
            matched = any(value.casefold() in item.casefold() for item in values)
        if matched:
            selected.append(record)
    return selected


def project_query_record(
    record: dict[str, Any], selected: list[str] | None
) -> dict[str, Any]:
    projected = dict(record)
    if selected is not None:
        fields = record.get("fields") or {}
        projected["fields"] = {name: fields.get(name) for name in selected}
    return projected


def query_quality(
    records: list[dict[str, Any]], expect: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    line_sizes = [
        max(0, int(item.get("line_end", 0)) - int(item.get("line_start", 0)) + 1)
        for item in records
    ]
    byte_sizes = [
        max(0, int(item.get("byte_end", 0)) - int(item.get("byte_start", 0)))
        for item in records
    ]
    confidences = [float(item.get("confidence", 0)) for item in records]
    structured = all(
        item.get("key") is not None and float(item.get("confidence", 0)) >= 0.6
        for item in records
    )
    metrics = {
        "matches": len(records),
        "max_record_lines": max(line_sizes, default=0),
        "max_record_bytes": max(byte_sizes, default=0),
        "total_bytes": sum(byte_sizes),
        "min_confidence": min(confidences, default=1.0),
        "structured": structured,
    }
    violations: list[dict[str, Any]] = []
    comparisons = {
        "max_record_lines": (metrics["max_record_lines"], "query_record_span_exceeded"),
        "max_record_bytes": (
            metrics["max_record_bytes"],
            "query_record_payload_exceeded",
        ),
        "max_total_bytes": (metrics["total_bytes"], "query_total_payload_exceeded"),
    }
    for key, (actual, code) in comparisons.items():
        if key in expect and actual > expect[key]:
            violations.append(
                diagnostic(
                    code,
                    "warning",
                    f"query quality limit {key} was exceeded",
                    details={"expected": expect[key], "actual": actual},
                )
            )
    if expect.get("structured") is True and records and not structured:
        violations.append(
            diagnostic(
                "query_unstructured_result",
                "warning",
                "query returned candidate-only evidence",
            )
        )
    if (
        "min_confidence" in expect
        and confidences
        and metrics["min_confidence"] < float(expect["min_confidence"])
    ):
        violations.append(
            diagnostic(
                "query_confidence_below_minimum",
                "warning",
                "query result confidence is below the declared minimum",
                details={
                    "expected": expect["min_confidence"],
                    "actual": metrics["min_confidence"],
                },
            )
        )
    return {
        "status": "failed" if violations else "passed",
        "metrics": metrics,
    }, violations


def command_run(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    if document.profile is None or document.profile.get("version") != 2:
        emit(
            {
                "schema": "mdq.query.v2",
                "status": "invalid",
                "count": 0,
                "records": [],
                "diagnostics": list(document.diagnostics)
                + [
                    diagnostic(
                        "query_contract_missing",
                        "error",
                        "named queries require an mdq v2 contract",
                    )
                ],
            }
        )
        return 3
    queries = document.profile.get("queries") or {}
    spec = queries.get(args.query)
    if spec is None:
        emit(
            {
                "schema": "mdq.query.v2",
                "status": "invalid",
                "count": 0,
                "records": [],
                "diagnostics": [
                    diagnostic(
                        "unknown_query",
                        "error",
                        f"query {args.query!r} is not declared",
                    )
                ],
            }
        )
        return 3
    when = spec.get("when")
    if when and regex_value(when["pattern"], args.value, None) is None:
        emit(
            {
                "schema": "mdq.query.v2",
                "status": "invalid",
                "count": 0,
                "records": [],
                "diagnostics": [
                    diagnostic(
                        "query_input_mismatch",
                        "error",
                        "query value does not satisfy the declared input pattern",
                    )
                ],
            }
        )
        return 3
    records, diagnostics = records_for_query(document)
    if error_diagnostics(diagnostics):
        emit(
            {
                "schema": "mdq.query.v2",
                "status": "invalid",
                "count": 0,
                "records": [],
                "diagnostics": diagnostics,
            }
        )
        return 3
    matched = query_matches(records, spec, args.value)
    quality, violations = query_quality(matched, spec.get("expect", {}))
    diagnostics.extend(violations)
    selected = spec.get("select")
    emit(
        {
            "schema": "mdq.query.v2",
            "status": "matched" if matched else "not_found",
            "query": args.query,
            "value": args.value,
            "count": len(matched),
            "records": [project_query_record(item, selected) for item in matched],
            "quality": quality,
            "diagnostics": diagnostics,
        }
    )
    return 0


def command_verify_queries(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    if document.profile is None or document.profile.get("version") != 2:
        diagnostics = list(document.diagnostics) + [
            diagnostic(
                "query_contract_missing",
                "error",
                "query verification requires an mdq v2 contract",
            )
        ]
        emit(
            {
                "schema": "mdq.verify.v2",
                "status": "invalid",
                "valid": False,
                "checks": [],
                "diagnostics": diagnostics,
            }
        )
        return 3
    queries = document.profile.get("queries") or {}
    if not queries:
        diagnostics = list(document.diagnostics) + [
            diagnostic(
                "query_contract_missing",
                "error",
                "the document declares no reusable query intents",
            )
        ]
        emit(
            {
                "schema": "mdq.verify.v2",
                "status": "invalid",
                "valid": False,
                "checks": [],
                "diagnostics": diagnostics,
            }
        )
        return 3
    records, diagnostics = records_for_query(document)
    checks: list[dict[str, Any]] = []
    for name, spec in queries.items():
        field_name = (
            "key" if spec["match"]["source"] == "key" else spec["match"]["field"]
        )
        buckets: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            for value in searchable_values(record, field_name):
                when = spec.get("when")
                if when and regex_value(when["pattern"], value, None) is None:
                    continue
                buckets.setdefault(value, []).append(record)
        worst_value, worst_records = max(
            buckets.items(),
            key=lambda item: (
                len(item[1]),
                max(
                    (
                        int(record.get("byte_end", 0))
                        - int(record.get("byte_start", 0))
                        for record in item[1]
                    ),
                    default=0,
                ),
            ),
            default=(None, []),
        )
        quality, violations = query_quality(worst_records, spec.get("expect", {}))
        if spec["match"].get("operator", "eq") == "contains":
            quality["static_analysis"] = (
                "exact-value lower bound; substring inputs are runtime-verified"
            )
        checks.append(
            {
                "query": name,
                "distinct_values": len(buckets),
                "worst_value": worst_value,
                "quality": quality,
                "diagnostics": violations,
            }
        )
        diagnostics.extend(violations)
    valid = not error_diagnostics(diagnostics) and all(
        item["quality"]["status"] == "passed" for item in checks
    )
    emit(
        {
            "schema": "mdq.verify.v2",
            "status": "verified" if valid else "failed",
            "valid": valid,
            "checks": checks,
            "diagnostics": diagnostics,
        }
    )
    return 0 if valid else 3


def replace_mdq_profile(raw: bytes, profile: dict[str, Any]) -> bytes:
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text[:4096] else "\n"
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        raise ValueError("adaptive profile repair requires YAML frontmatter")
    closing = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].strip() in {"---", "..."}
        ),
        None,
    )
    if closing is None:
        raise ValueError("adaptive profile repair requires complete YAML frontmatter")
    mdq_start = next(
        (
            index
            for index in range(1, closing)
            if re.match(r"^mdq[ \t]*:", lines[index])
        ),
        None,
    )
    if mdq_start is None:
        raise ValueError(
            "adaptive profile repair requires an existing top-level mdq block"
        )
    mdq_end = closing
    for index in range(mdq_start + 1, closing):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t", "#")):
            mdq_end = index
            break
    dumped = yaml.safe_dump(
        profile,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).rstrip("\n")
    block = (
        "mdq:"
        + newline
        + newline.join(f"  {line}" for line in dumped.splitlines())
        + newline
    )
    return ("".join(lines[:mdq_start]) + block + "".join(lines[mdq_end:])).encode(
        "utf-8"
    )


def table_repair_candidate(
    document: SourceDocument, requested: str, query_name: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    headings, _code_lines, _markers, parse_diagnostics = analyze_markdown(
        document, "gfm"
    )
    tables, table_diagnostics = analyze_tables(document, headings)
    matches: list[tuple[MarkdownTable, dict[str, Any]]] = []
    for table in tables:
        for candidate in table_key_candidates(table):
            if any(
                regex_value(
                    candidate["pattern"],
                    row.cells[candidate["column"]],
                    candidate["group"],
                )
                == requested
                for row in table.rows
            ):
                matches.append((table, candidate))
    diagnostics = parse_diagnostics + table_diagnostics
    if len(matches) != 1:
        if len(matches) > 1:
            diagnostics.append(
                diagnostic(
                    "query_contract_repair_ambiguous",
                    "warning",
                    "multiple table schemas could define the requested identity",
                )
            )
        return None, diagnostics
    candidate_profile = table_profile(*matches[0])
    candidate_profile["queries"][query_name] = candidate_profile["queries"].pop("by_id")
    if document.profile:
        for key in ("actors", "maintenance", "index"):
            if key in document.profile:
                candidate_profile[key] = json.loads(json.dumps(document.profile[key]))
    return candidate_profile, diagnostics


def query_refinement_candidate(
    profile: dict[str, Any],
    records: list[dict[str, Any]],
    query_name: str,
    value: str,
) -> dict[str, Any] | None:
    original = profile["queries"][query_name]
    original_matches = query_matches(records, original, value)
    original_quality, _ = query_quality(original_matches, original.get("expect", {}))
    if original_quality["status"] == "passed":
        return None
    alternatives: list[tuple[int, str]] = []
    operator = original["match"].get("operator", "eq")
    for field_name in profile.get("fields", {}):
        alternative = json.loads(json.dumps(original))
        alternative["match"] = {
            "source": "field",
            "field": field_name,
            "operator": operator,
        }
        matched = query_matches(records, alternative, value)
        quality, _ = query_quality(matched, alternative.get("expect", {}))
        if (
            matched
            and quality["status"] == "passed"
            and len(matched) < len(original_matches)
        ):
            alternatives.append((len(matched), field_name))
    if not alternatives:
        return None
    best_count = min(item[0] for item in alternatives)
    best = [field_name for count, field_name in alternatives if count == best_count]
    if len(best) != 1:
        return None
    candidate = json.loads(json.dumps(profile))
    candidate["queries"][query_name]["match"] = {
        "source": "field",
        "field": best[0],
        "operator": operator,
    }
    return candidate


def command_optimize(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    if document.profile is None:
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": list(document.diagnostics)
                + [
                    diagnostic(
                        "persistent_contract_required",
                        "error",
                        "optimization requires an existing mdq contract",
                    )
                ],
            }
        )
        return 3
    query_name = args.query or "by_id"
    requested = args.value if args.query else args.id
    if args.query and requested is None:
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": [
                    diagnostic(
                        "query_input_missing",
                        "error",
                        "--value is required with --query",
                    )
                ],
            }
        )
        return 3
    assert requested is not None
    records, diagnostics = records_for_query(document)
    candidate: dict[str, Any] | None = None
    scopes: set[str] = set()
    if (
        args.query
        and document.profile.get("version") == 2
        and query_name in (document.profile.get("queries") or {})
    ):
        candidate = query_refinement_candidate(
            document.profile, records, query_name, requested
        )
        if candidate is not None:
            scopes = {"queries"}
    if candidate is None:
        candidate, repair_diagnostics = table_repair_candidate(
            document, requested, query_name
        )
        diagnostics.extend(repair_diagnostics)
        if candidate is not None:
            scopes = {"records", "fields", "queries"}
    if candidate is None:
        diagnostics.append(
            diagnostic(
                "query_contract_repair_unavailable",
                "info",
                "no unique deterministic contract refinement satisfied the failed query",
            )
        )
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "unchanged",
                "applied": False,
                "query": query_name,
                "value": requested,
                "diagnostics": diagnostics,
            }
        )
        return 0

    candidate_diagnostics: list[dict[str, Any]] = []
    validated = validate_profile(candidate, candidate_diagnostics)
    if validated is None:
        diagnostics.extend(candidate_diagnostics)
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": diagnostics,
            }
        )
        return 3
    candidate_raw = replace_mdq_profile(document.raw, validated)
    candidate_document = parse_document(document.path, candidate_raw)
    candidate_records, verification_diagnostics = records_for_query(candidate_document)
    diagnostics.extend(candidate_diagnostics + verification_diagnostics)
    candidate_spec = candidate_document.profile["queries"][query_name]
    candidate_matches = query_matches(candidate_records, candidate_spec, requested)
    quality, quality_diagnostics = query_quality(
        candidate_matches, candidate_spec.get("expect", {})
    )
    diagnostics.extend(quality_diagnostics)
    old_keys = {
        str(item["key"])
        for item in records
        if item.get("key") is not None and float(item.get("confidence", 0)) >= 0.6
    }
    new_keys = {
        str(item["key"])
        for item in candidate_records
        if item.get("key") is not None and float(item.get("confidence", 0)) >= 0.6
    }
    missing_keys = sorted(old_keys - new_keys)
    duplicate_keys = [
        item for item in diagnostics if item.get("code") == "duplicate_key"
    ]
    if (
        quality["status"] != "passed"
        or len(candidate_matches) != 1
        or missing_keys
        or duplicate_keys
    ):
        if missing_keys:
            diagnostics.append(
                diagnostic(
                    "query_contract_key_loss",
                    "error",
                    "candidate repair would remove existing record identities",
                    details={"keys": missing_keys},
                )
            )
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "quality": quality,
                "diagnostics": diagnostics,
            }
        )
        return 3
    policy = (document.profile.get("maintenance") or {}).get("query_contract") or {}
    if args.apply and policy.get("mode") == "locked":
        diagnostics.append(
            diagnostic(
                "query_contract_locked",
                "error",
                "the document locks automatic query-contract changes",
            )
        )
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": diagnostics,
            }
        )
        return 3
    allowed = set(policy.get("allow") or scopes)
    if args.apply and not scopes <= allowed:
        diagnostics.append(
            diagnostic(
                "query_contract_scope_denied",
                "error",
                "the repair requires maintenance scopes that are not allowed",
                details={"required": sorted(scopes), "allowed": sorted(allowed)},
            )
        )
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": diagnostics,
            }
        )
        return 3
    candidate_index_path, candidate_index_bytes, index_diagnostics = index_bytes(
        candidate_document
    )
    diagnostics.extend(index_diagnostics)
    if candidate_index_path is not None and candidate_index_bytes is None:
        diagnostics.append(
            diagnostic(
                "index_rebuild_failed",
                "error",
                "the declared index could not be prepared from the repaired contract",
            )
        )
        emit(
            {
                "schema": "mdq.optimize.v2",
                "status": "invalid",
                "applied": False,
                "diagnostics": diagnostics,
            }
        )
        return 3
    if args.apply:
        if document.path.read_bytes() != document.raw:
            diagnostics.append(
                diagnostic(
                    "source_changed",
                    "error",
                    "source changed after optimization preflight",
                )
            )
            emit(
                {
                    "schema": "mdq.optimize.v2",
                    "status": "invalid",
                    "applied": False,
                    "diagnostics": diagnostics,
                }
            )
            return 4
        original_index_exists = bool(
            candidate_index_path is not None and candidate_index_path.exists()
        )
        original_index_bytes = (
            candidate_index_path.read_bytes()
            if candidate_index_path is not None and original_index_exists
            else None
        )
        try:
            atomic_write_bytes(document.path, candidate_raw)
            if candidate_index_path is not None and candidate_index_bytes is not None:
                atomic_write_bytes(candidate_index_path, candidate_index_bytes)
            written_document = read_document(document.path)
            written_records, written_diagnostics = records_for_query(written_document)
            written_spec = written_document.profile["queries"][query_name]
            written_matches = query_matches(written_records, written_spec, requested)
            written_quality, written_quality_diagnostics = query_quality(
                written_matches, written_spec.get("expect", {})
            )
            diagnostics.extend(written_diagnostics + written_quality_diagnostics)
            if (
                error_diagnostics(written_diagnostics)
                or len(written_matches) != 1
                or written_quality["status"] != "passed"
            ):
                raise RuntimeError("post-write query verification failed")
        except Exception as exc:
            rollback_errors: list[str] = []
            try:
                atomic_write_bytes(document.path, document.raw)
            except Exception as rollback_exc:
                rollback_errors.append(f"source: {rollback_exc}")
            if candidate_index_path is not None:
                try:
                    if original_index_exists and original_index_bytes is not None:
                        atomic_write_bytes(candidate_index_path, original_index_bytes)
                    elif candidate_index_path.exists():
                        candidate_index_path.unlink()
                except Exception as rollback_exc:
                    rollback_errors.append(f"index: {rollback_exc}")
            diagnostics.append(
                diagnostic(
                    "query_contract_write_failed",
                    "error",
                    "the repaired contract or its declared index could not be written",
                    details={"error": str(exc)},
                )
            )
            if rollback_errors:
                diagnostics.append(
                    diagnostic(
                        "query_contract_rollback_failed",
                        "error",
                        "one or more files could not be restored after the write failure",
                        details={"errors": rollback_errors},
                    )
                )
            emit(
                {
                    "schema": "mdq.optimize.v2",
                    "status": "invalid",
                    "applied": False,
                    "diagnostics": diagnostics,
                }
            )
            return 4
        diagnostics.append(
            diagnostic(
                "query_contract_repaired",
                "info",
                "the mdq control block was updated after in-memory verification",
            )
        )
    else:
        diagnostics.append(
            diagnostic(
                "query_contract_repair_planned",
                "info",
                "a deterministic mdq control-block repair is available",
            )
        )
    emit(
        {
            "schema": "mdq.optimize.v2",
            "status": "updated" if args.apply else "planned",
            "applied": bool(args.apply),
            "query": query_name,
            "value": requested,
            "scopes": sorted(scopes),
            "index_rebuilt": bool(args.apply and candidate_index_path is not None),
            "quality": quality,
            "candidate_profile": validated,
            "diagnostics": diagnostics,
        }
    )
    return 0


def command_search(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    preparation_diagnostics = prepare_temporary_profile(document, args, requested=None)
    if document.profile is None:
        if error_diagnostics(document.diagnostics):
            emit(
                {
                    "status": "invalid",
                    "count": 0,
                    "records": [],
                    "candidates": [],
                    "diagnostics": document.diagnostics,
                }
            )
            return 3
        if args.field not in {None, "body", "context"}:
            diagnostics = (
                list(document.diagnostics)
                + preparation_diagnostics
                + [
                    diagnostic(
                        "unknown_field",
                        "error",
                        f"field {args.field!r} is unavailable without a record boundary",
                    )
                ]
            )
            emit(
                {
                    "status": "invalid",
                    "count": 0,
                    "records": [],
                    "candidates": [],
                    "diagnostics": diagnostics,
                }
            )
            return 3
        local, parse_diagnostics = line_local_search_records(
            document, args.text, args.limit
        )
        diagnostics = (
            list(document.diagnostics) + preparation_diagnostics + parse_diagnostics
        )
        if not local:
            diagnostics.append(
                diagnostic(
                    "no_match", "info", f"literal text {args.text!r} was not found"
                )
            )
        emit(
            {
                "status": "matched" if local else "not_found",
                "count": len(local),
                "records": local,
                "candidates": [],
                "diagnostics": diagnostics,
            }
        )
        return 0
    temporary = (document.profile_source or "").startswith(TEMPORARY_PROFILE_PREFIX)
    if (
        args.field
        and args.field != "key"
        and args.field not in document.profile.get("fields", {})
    ):
        diagnostics = list(document.diagnostics) + [
            diagnostic(
                "unknown_field", "error", f"field {args.field!r} is not declared"
            )
        ]
        emit(
            {
                "status": "invalid",
                "count": 0,
                "records": [],
                "candidates": [],
                "diagnostics": diagnostics,
            }
        )
        return 3
    records, diagnostics = records_for_query(document)
    if error_diagnostics(diagnostics):
        emit(
            {
                "status": "invalid",
                "count": 0,
                "records": [],
                "candidates": [],
                "diagnostics": diagnostics,
            }
        )
        return 3
    needle = args.text.casefold()
    matched: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for item in records:
        values = searchable_values(item, args.field)
        if temporary and args.field is None:
            values = (
                searchable_values(item, "key")
                + searchable_values(item, "title")
                + [visible_record_text(document, item, include_heading=False)]
            )
        elif temporary and args.field == "body":
            values = [visible_record_text(document, item, include_heading=False)]
        if any(needle in value.casefold() for value in values):
            if float(item.get("confidence", 0)) >= 0.6 and (
                temporary or item.get("key") is not None
            ):
                matched.append(item)
            else:
                candidate = dict(item)
                candidate["candidate"] = True
                candidates.append(candidate)
        if len(matched) + len(candidates) >= args.limit:
            break
    if temporary and args.field is None and len(matched) + len(candidates) < args.limit:
        local, _local_diagnostics = line_local_search_records(
            document, args.text, args.limit - len(matched) - len(candidates)
        )
        covered = [
            (int(item.get("line_start", 1)), int(item.get("line_end", 0)))
            for item in records
        ]
        matched.extend(
            item
            for item in local
            if not any(
                start <= int(item.get("line_start", 0)) <= end for start, end in covered
            )
        )
    if not matched and not candidates:
        diagnostics.append(
            diagnostic("no_match", "info", f"literal text {args.text!r} was not found")
        )
    emit(
        {
            "status": "matched" if matched else "not_found",
            "count": len(matched),
            "records": matched,
            "candidates": candidates,
            "diagnostics": diagnostics,
        }
    )
    return 0


def collection_diagnostic(
    item: dict[str, Any], document: Path, relative_path: str
) -> dict[str, Any]:
    enriched = dict(item)
    enriched["document"] = str(document)
    enriched["relative_path"] = relative_path
    return enriched


def collection_paths(
    targets: list[Path],
    patterns: list[str],
    *,
    reject_matched_symlinks: bool = False,
) -> tuple[Path, list[tuple[Path, str]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    candidates: dict[Path, None] = {}
    roots: list[Path] = []

    for target in targets:
        if target.is_symlink():
            diagnostics.append(
                diagnostic(
                    "collection_path_unsafe",
                    "error",
                    f"collection path must not be a symlink: {target}",
                )
            )
            continue
        resolved = target.resolve()
        if resolved.is_file():
            if resolved.suffix.casefold() != ".md":
                diagnostics.append(
                    diagnostic(
                        "collection_path_invalid",
                        "error",
                        f"collection file must use the .md extension: {target}",
                    )
                )
                continue
            roots.append(resolved.parent)
            candidates[resolved] = None
            continue
        if not resolved.is_dir():
            diagnostics.append(
                diagnostic(
                    "collection_path_invalid",
                    "error",
                    f"collection path must be a Markdown file or directory: {target}",
                )
            )
            continue

        roots.append(resolved)
        for pattern in patterns:
            pattern_path = Path(pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts:
                diagnostics.append(
                    diagnostic(
                        "collection_glob_unsafe",
                        "error",
                        f"collection glob must stay inside the target directory: {pattern}",
                    )
                )
                continue
            try:
                matches = resolved.glob(pattern)
            except (OSError, ValueError) as exc:
                diagnostics.append(
                    diagnostic(
                        "collection_glob_invalid",
                        "error",
                        f"collection glob {pattern!r} is invalid: {exc}",
                    )
                )
                continue
            for candidate in matches:
                if candidate.is_symlink():
                    if reject_matched_symlinks and candidate.suffix.casefold() == ".md":
                        diagnostics.append(
                            diagnostic(
                                "collection_path_unsafe",
                                "error",
                                f"matched Markdown path must not be a symlink: {candidate}",
                            )
                        )
                    continue
                if not candidate.is_file() or candidate.suffix.casefold() != ".md":
                    continue
                actual = candidate.resolve()
                try:
                    actual.relative_to(resolved)
                except ValueError:
                    diagnostics.append(
                        diagnostic(
                            "collection_path_unsafe",
                            "error",
                            f"matched document escapes the collection root: {candidate}",
                        )
                    )
                    continue
                candidates[actual] = None

    root = (
        Path(os.path.commonpath([str(item) for item in roots]))
        if roots
        else Path.cwd().resolve()
    )
    ordered = sorted(
        (
            path,
            (path.relative_to(root).as_posix() if path != root else path.name),
        )
        for path in candidates
    )
    return root, ordered, diagnostics


def collection_record(
    record: dict[str, Any],
    *,
    document: SourceDocument,
    relative_path: str,
    field_name: str | None,
) -> dict[str, Any]:
    item = dict(record)
    item["document"] = str(document.path)
    item["relative_path"] = relative_path
    if field_name is not None and field_name != "key":
        fields = record.get("fields") or {}
        item["fields"] = {field_name: fields.get(field_name)}
    elif field_name == "key":
        item["fields"] = {}
    return item


def command_scan(args: argparse.Namespace) -> int:
    patterns = list(args.glob or ["**/*.md"])
    root, paths, diagnostics = collection_paths(
        [Path(item) for item in args.path], patterns
    )
    if error_diagnostics(diagnostics):
        emit(
            {
                "schema": "mdq.collection.v1",
                "status": "invalid",
                "root": str(root),
                "globs": patterns,
                "documents_scanned": 0,
                "documents_matched": 0,
                "count": 0,
                "truncated": False,
                "records": [],
                "candidates": [],
                "documents": [],
                "diagnostics": diagnostics,
            }
        )
        return 3

    requested_ids = {item.strip() for item in (args.id or [])}
    matched_records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    document_summaries: list[dict[str, Any]] = []
    invalid_documents = 0
    documents_matched = 0
    truncated = False

    for path, relative_path in paths:
        try:
            document = read_document(path)
        except (OSError, UnicodeDecodeError) as exc:
            code = (
                "encoding_invalid"
                if isinstance(exc, UnicodeDecodeError)
                else "io_error"
            )
            item = diagnostic(code, "error", str(exc))
            diagnostics.append(collection_diagnostic(item, path, relative_path))
            document_summaries.append(
                {
                    "document": str(path),
                    "relative_path": relative_path,
                    "status": "invalid",
                    "profile_source": None,
                    "record_count": 0,
                    "matched_count": 0,
                    "diagnostics": [item],
                }
            )
            invalid_documents += 1
            continue

        preparation_diagnostics: list[dict[str, Any]] = []
        document_diagnostics = list(document.diagnostics)
        if args.require_contract and document.profile is None:
            document_diagnostics.append(
                diagnostic(
                    "persistent_contract_required",
                    "error",
                    "collection query requires a valid persistent mdq contract",
                    line=1,
                )
            )
        elif document.profile is None:
            preparation_diagnostics = prepare_temporary_profile(
                document,
                args,
                requested=next(iter(requested_ids))
                if len(requested_ids) == 1
                else None,
            )
            document_diagnostics = list(document.diagnostics)

        if (
            document.profile is not None
            and args.field not in {None, "key"}
            and args.field not in document.profile.get("fields", {})
        ):
            document_diagnostics.append(
                diagnostic(
                    "unknown_field",
                    "error",
                    f"field {args.field!r} is not declared",
                )
            )

        records: list[dict[str, Any]] = []
        if document.profile is not None and not error_diagnostics(document_diagnostics):
            try:
                records, extracted_diagnostics = records_for_query(document)
            except TimeoutError:
                extracted_diagnostics = [
                    diagnostic(
                        "regex_timeout",
                        "error",
                        "a profile regex exceeded the matching time limit",
                    )
                ]
            all_document_diagnostics = (
                document_diagnostics + preparation_diagnostics + extracted_diagnostics
            )
        else:
            all_document_diagnostics = document_diagnostics + preparation_diagnostics
        document_invalid = error_diagnostics(all_document_diagnostics)
        if document_invalid:
            invalid_documents += 1

        structured: list[dict[str, Any]] = []
        document_candidates: list[dict[str, Any]] = []
        for record in records:
            confidence = float(record.get("confidence", 0.0))
            key = record.get("key")
            selected = key is not None and confidence >= 0.6
            if requested_ids:
                selected = selected and key in requested_ids
            if args.text is not None:
                values = searchable_values(record, args.field)
                selected = selected and any(
                    args.text.casefold() in value.casefold() for value in values
                )
            item = collection_record(
                record,
                document=document,
                relative_path=relative_path,
                field_name=args.field,
            )
            if selected:
                structured.append(item)
            elif key is None or confidence < 0.6:
                item["candidate"] = True
                document_candidates.append(item)

        if structured:
            documents_matched += 1
        for item in structured:
            if len(matched_records) < args.limit:
                matched_records.append(item)
            else:
                truncated = True
        for item in document_candidates:
            if len(candidates) < args.limit:
                candidates.append(item)
            else:
                truncated = True

        document_status = (
            "invalid" if document_invalid else "matched" if structured else "not_found"
        )
        document_summaries.append(
            {
                "document": str(document.path),
                "relative_path": relative_path,
                "status": document_status,
                "profile_source": document.profile_source,
                "record_count": len(
                    [
                        item
                        for item in records
                        if item.get("key") is not None
                        and float(item.get("confidence", 0.0)) >= 0.6
                    ]
                ),
                "matched_count": len(structured),
                "diagnostics": all_document_diagnostics,
            }
        )
        diagnostics.extend(
            collection_diagnostic(item, document.path, relative_path)
            for item in all_document_diagnostics
        )

    if invalid_documents:
        collection_status = "partial" if matched_records else "invalid"
    else:
        collection_status = "matched" if matched_records else "not_found"
    emit(
        {
            "schema": "mdq.collection.v1",
            "status": collection_status,
            "root": str(root),
            "globs": patterns,
            "documents_scanned": len(paths),
            "documents_matched": documents_matched,
            "count": len(matched_records),
            "truncated": truncated,
            "records": matched_records,
            "candidates": candidates,
            "documents": document_summaries,
            "diagnostics": diagnostics,
        }
    )
    return 3 if invalid_documents else 0


def parse_where_conditions(
    values: list[str],
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    conditions: list[tuple[str, str]] = []
    diagnostics: list[dict[str, Any]] = []
    for raw in values:
        if "=" not in raw:
            diagnostics.append(
                diagnostic(
                    "condition_invalid",
                    "error",
                    f"condition must use FIELD=VALUE syntax: {raw!r}",
                )
            )
            continue
        name, value = raw.split("=", 1)
        name = name.strip()
        if not name:
            diagnostics.append(
                diagnostic(
                    "condition_invalid",
                    "error",
                    f"condition field must not be empty: {raw!r}",
                )
            )
            continue
        conditions.append((name, value))
    return conditions, diagnostics


def record_body_start(record: Record) -> int:
    start = record.start
    if record.marker is not None and start == record.marker.line:
        start = record.marker.line + 1
    if record.heading is not None:
        start = max(start, record.heading.end)
    return start


def label_field_value_span(
    document: SourceDocument,
    record: Record,
    spec: dict[str, Any],
    code_lines: set[int],
) -> tuple[int, int, int] | None:
    occurrences = label_occurrences(
        document,
        record_body_start(record),
        record.end + 1,
        spec["labels"],
        code_lines,
    )
    if len(occurrences) != 1:
        return None
    line_index = int(occurrences[0]["line"]) - 1
    masked = document.masked_lines[line_index].rstrip("\r\n")
    wanted = {normalize_label(item) for item in spec["labels"]}
    local_start: int | None = None
    local_end: int | None = None

    stripped = masked.strip()
    if stripped.startswith("|") and stripped.count("|") >= 2:
        bars = [index for index, char in enumerate(masked) if char == "|"]
        if len(bars) >= 3:
            label_cell = masked[bars[0] + 1 : bars[1]]
            if normalize_label(label_cell) in wanted:
                value_begin = bars[1] + 1
                value_finish = bars[2]
                value_text = masked[value_begin:value_finish]
                local_start = (
                    value_begin + len(value_text) - len(value_text.lstrip(" \t"))
                )
                local_end = value_finish - (
                    len(value_text) - len(value_text.rstrip(" \t"))
                )
    else:
        match = re.match(
            r"^[ \t]*(?:(?:>[ \t]*)+)?(?:[-*+][ \t]+)?"
            r"(?P<label>(?:\*\*|__|`)?[^:：|]+?(?:\*\*|__|`)?)"
            r"[ \t]*[:：][ \t]*(?P<value>.*)$",
            masked,
        )
        if match and normalize_label(match.group("label")) in wanted:
            value_text = match.group("value")
            local_start = match.start("value")
            local_end = match.end("value") - (
                len(value_text) - len(value_text.rstrip(" \t"))
            )

    if local_start is None or local_end is None or local_end <= local_start:
        return None
    line_offset = sum(len(line) for line in document.lines[:line_index])
    return line_offset + local_start, line_offset + local_end, line_index + 1


def extract_record_objects(
    document: SourceDocument,
) -> tuple[list[Record], set[int], list[dict[str, Any]]]:
    if document.profile is None:
        return [], set(), list(document.diagnostics)
    headings, code_lines, markers, parse_diagnostics = analyze_markdown(
        document, document.profile.get("dialect", "commonmark")
    )
    tables, table_diagnostics = analyze_tables(document, headings)
    records, record_diagnostics = build_records(
        document, document.profile, headings, code_lines, markers, tables
    )
    return (
        records,
        code_lines,
        list(document.diagnostics)
        + parse_diagnostics
        + table_diagnostics
        + record_diagnostics,
    )


def apply_text_patches(text: str, patches: list[tuple[int, int, str]]) -> str:
    result = text
    previous_start = len(text) + 1
    for start, end, replacement in sorted(patches, reverse=True):
        if end > previous_start or start < 0 or end < start or end > len(text):
            raise ValueError("field value patches overlap or escape the document")
        result = result[:start] + replacement + result[end:]
        previous_start = start
    return result


def index_bytes(
    document: SourceDocument,
) -> tuple[Path | None, bytes | None, list[dict[str, Any]]]:
    if document.profile is None or "index" not in document.profile:
        return None, None, []
    path, problem = index_path(document)
    if problem is not None:
        return None, None, [problem]
    assert path is not None
    records, diagnostics = extract_current(document)
    if error_diagnostics(diagnostics):
        return path, None, diagnostics
    payload = {
        "index_schema": INDEX_SCHEMA,
        "engine": ENGINE,
        "protocol_version": document.profile["version"],
        "source": str(document.path),
        "source_sha256": document.source_hash,
        "profile_sha256": document.profile_hash,
        "records": records,
        "diagnostics": diagnostics,
    }
    return (
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        diagnostics,
    )


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.mdq-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        mode = path.stat().st_mode if path.exists() else 0o644
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def command_set(args: argparse.Namespace) -> int:
    patterns = list(args.glob or ["**/*.md"])
    root, paths, diagnostics = collection_paths(
        [Path(item) for item in args.path],
        patterns,
        reject_matched_symlinks=True,
    )
    conditions, condition_diagnostics = parse_where_conditions(args.where or [])
    diagnostics.extend(condition_diagnostics)
    requested_ids = {item.strip() for item in (args.id or [])}
    if any(not item for item in requested_ids):
        diagnostics.append(
            diagnostic("selector_invalid", "error", "record IDs must not be empty")
        )
    if (
        not args.field.strip()
        or args.value != args.value.strip()
        or "\n" in args.value
        or "\r" in args.value
        or args.value == ""
    ):
        diagnostics.append(
            diagnostic(
                "mutation_value_invalid",
                "error",
                "field and value must be non-empty single-line text without surrounding whitespace",
            )
        )
    if error_diagnostics(diagnostics):
        emit(
            {
                "schema": "mdq.mutation.v1",
                "status": "invalid",
                "applied": False,
                "root": str(root),
                "documents_scanned": 0,
                "count": 0,
                "change_count": 0,
                "changes": [],
                "documents": [],
                "diagnostics": diagnostics,
            }
        )
        return 3

    changes: list[dict[str, Any]] = []
    document_summaries: list[dict[str, Any]] = []
    planned_sources: dict[Path, bytes] = {}
    planned_indexes: dict[Path, bytes] = {}
    original_sources: dict[Path, bytes] = {}
    found_ids: set[str] = set()
    changed_documents: dict[Path, SourceDocument] = {}

    for path, relative_path in paths:
        document_diagnostics: list[dict[str, Any]] = []
        try:
            document = read_document(path)
        except (OSError, UnicodeDecodeError) as exc:
            code = (
                "encoding_invalid"
                if isinstance(exc, UnicodeDecodeError)
                else "io_error"
            )
            document_diagnostics.append(diagnostic(code, "error", str(exc)))
            document_summaries.append(
                {
                    "document": str(path),
                    "relative_path": relative_path,
                    "status": "invalid",
                    "selected_count": 0,
                    "change_count": 0,
                    "diagnostics": document_diagnostics,
                }
            )
            diagnostics.extend(
                collection_diagnostic(item, path, relative_path)
                for item in document_diagnostics
            )
            continue

        if document.profile is None or (document.profile_source or "").startswith(
            TEMPORARY_PROFILE_PREFIX
        ):
            document_diagnostics.extend(document.diagnostics)
            document_diagnostics.append(
                diagnostic(
                    "persistent_contract_required",
                    "error",
                    "batch updates require a valid persistent mdq contract",
                    line=1,
                )
            )
            records: list[Record] = []
            code_lines: set[int] = set()
        else:
            records, code_lines, extracted_diagnostics = extract_record_objects(
                document
            )
            document_diagnostics.extend(extracted_diagnostics)

        profile_fields = (
            document.profile.get("fields", {}) if document.profile is not None else {}
        )
        target_spec = profile_fields.get(args.field)
        if document.profile is not None and target_spec is None:
            document_diagnostics.append(
                diagnostic(
                    "unknown_field",
                    "error",
                    f"field {args.field!r} is not declared",
                )
            )
        elif target_spec is not None and (
            target_spec.get("source") != "label"
            or "pattern" in target_spec
            or "group" in target_spec
        ):
            document_diagnostics.append(
                diagnostic(
                    "field_not_writable",
                    "error",
                    f"field {args.field!r} must be an untransformed source: label scalar",
                )
            )
        for condition_field, _condition_value in conditions:
            if condition_field not in profile_fields:
                document_diagnostics.append(
                    diagnostic(
                        "unknown_field",
                        "error",
                        f"condition field {condition_field!r} is not declared",
                    )
                )

        structured = [
            item for item in records if item.key is not None and item.confidence >= 0.6
        ]
        duplicate_keys = {
            key
            for key, count in Counter(item.key for item in structured).items()
            if count > 1
        }
        if duplicate_keys:
            document_diagnostics.append(
                diagnostic(
                    "duplicate_key",
                    "error",
                    "batch updates refuse documents containing duplicate record keys",
                    details={"keys": sorted(duplicate_keys)},
                )
            )

        selected: list[Record] = []
        if not error_diagnostics(document_diagnostics):
            for record in structured:
                assert record.key is not None
                if requested_ids and record.key not in requested_ids:
                    continue
                if requested_ids:
                    found_ids.add(record.key)
                if not all(
                    record.fields.get(name) == expected for name, expected in conditions
                ):
                    continue
                selected.append(record)

        document_changes: list[dict[str, Any]] = []
        patches: list[tuple[int, int, str]] = []
        if target_spec is not None:
            for record in selected:
                current = record.fields.get(args.field)
                if current is None:
                    document_diagnostics.append(
                        diagnostic(
                            "missing_field",
                            "error",
                            f"field {args.field!r} is absent or conflicting in record {record.key!r}",
                            line=record.start + 1,
                        )
                    )
                    continue
                located = label_field_value_span(
                    document, record, target_spec, code_lines
                )
                if located is None:
                    document_diagnostics.append(
                        diagnostic(
                            "field_location_ambiguous",
                            "error",
                            f"field {args.field!r} does not have one source-exact label value in record {record.key!r}",
                            line=record.start + 1,
                        )
                    )
                    continue
                start, end, line = located
                changed = str(current) != args.value
                item = {
                    "document": str(document.path),
                    "relative_path": relative_path,
                    "key": record.key,
                    "field": args.field,
                    "before": current,
                    "after": args.value,
                    "line": line,
                    "changed": changed,
                }
                document_changes.append(item)
                if changed:
                    patches.append((start, end, args.value))

        patched_document: SourceDocument | None = None
        if not error_diagnostics(document_diagnostics) and patches:
            try:
                patched_text = apply_text_patches(document.text, patches)
                patched_document = parse_document(
                    document.path, patched_text.encode("utf-8")
                )
                patched_records, _patched_code, patched_diagnostics = (
                    extract_record_objects(patched_document)
                )
                document_diagnostics.extend(patched_diagnostics)
                patched_by_key = {
                    item.key: item
                    for item in patched_records
                    if item.key is not None and item.confidence >= 0.6
                }
                for item in document_changes:
                    updated = patched_by_key.get(item["key"])
                    if updated is None or updated.fields.get(args.field) != args.value:
                        document_diagnostics.append(
                            diagnostic(
                                "mutation_verification_failed",
                                "error",
                                f"updated field {args.field!r} did not round-trip for record {item['key']!r}",
                            )
                        )
                index_target, content, index_diagnostics = index_bytes(patched_document)
                document_diagnostics.extend(index_diagnostics)
                if index_target is not None and content is not None:
                    if index_target in planned_indexes:
                        document_diagnostics.append(
                            diagnostic(
                                "batch_path_conflict",
                                "error",
                                f"multiple documents declare the same index path: {index_target}",
                            )
                        )
                    else:
                        planned_indexes[index_target] = content
            except (UnicodeDecodeError, ValueError, TimeoutError) as exc:
                document_diagnostics.append(
                    diagnostic(
                        "mutation_preflight_failed",
                        "error",
                        f"could not validate the planned source patch: {exc}",
                    )
                )

        if not error_diagnostics(document_diagnostics):
            changes.extend(document_changes)
            if patched_document is not None:
                original_sources[document.path] = document.raw
                planned_sources[document.path] = patched_document.raw
                changed_documents[document.path] = patched_document
        document_status = (
            "invalid"
            if error_diagnostics(document_diagnostics)
            else "planned"
            if patches
            else "unchanged"
            if selected
            else "not_found"
        )
        document_summaries.append(
            {
                "document": str(document.path),
                "relative_path": relative_path,
                "status": document_status,
                "selected_count": len(selected),
                "change_count": len(patches),
                "diagnostics": document_diagnostics,
            }
        )
        diagnostics.extend(
            collection_diagnostic(item, document.path, relative_path)
            for item in document_diagnostics
        )

    missing_ids = sorted(requested_ids - found_ids)
    if missing_ids:
        diagnostics.append(
            diagnostic(
                "no_match",
                "error",
                "one or more requested record IDs were not found in the collection",
                details={"ids": missing_ids},
            )
        )
    source_paths = {path for path, _relative_path in paths}
    conflicting_indexes = sorted(
        str(path) for path in planned_indexes if path in source_paths
    )
    if conflicting_indexes:
        diagnostics.append(
            diagnostic(
                "batch_path_conflict",
                "error",
                "a declared index path overlaps a selected Markdown source",
                details={"paths": conflicting_indexes},
            )
        )
    if error_diagnostics(diagnostics):
        emit(
            {
                "schema": "mdq.mutation.v1",
                "status": "invalid",
                "applied": False,
                "root": str(root),
                "documents_scanned": len(paths),
                "count": len(changes),
                "change_count": len([item for item in changes if item["changed"]]),
                "changes": changes,
                "documents": document_summaries,
                "diagnostics": diagnostics,
            }
        )
        return 3

    change_count = len([item for item in changes if item["changed"]])
    if not args.apply:
        status = "planned" if change_count else "unchanged" if changes else "not_found"
        emit(
            {
                "schema": "mdq.mutation.v1",
                "status": status,
                "applied": False,
                "root": str(root),
                "documents_scanned": len(paths),
                "count": len(changes),
                "change_count": change_count,
                "changes": changes,
                "documents": document_summaries,
                "diagnostics": diagnostics,
            }
        )
        return 0

    outputs = {**planned_sources, **planned_indexes}
    originals: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None for path in outputs
    }
    drifted = [
        str(path)
        for path, original in original_sources.items()
        if path.read_bytes() != original
    ]
    if drifted:
        diagnostics.append(
            diagnostic(
                "source_changed",
                "error",
                "source changed after preflight; no batch update was applied",
                details={"paths": drifted},
            )
        )
        emit(
            {
                "schema": "mdq.mutation.v1",
                "status": "invalid",
                "applied": False,
                "root": str(root),
                "documents_scanned": len(paths),
                "count": len(changes),
                "change_count": change_count,
                "changes": changes,
                "documents": document_summaries,
                "diagnostics": diagnostics,
            }
        )
        return 4

    written: list[Path] = []
    try:
        for path, content in outputs.items():
            atomic_write_bytes(path, content)
            written.append(path)
        for source_path, expected_document in changed_documents.items():
            current = read_document(source_path)
            if current.raw != expected_document.raw:
                raise RuntimeError(f"written source bytes differ: {source_path}")
            records, verify_diagnostics = extract_current(current)
            if error_diagnostics(verify_diagnostics):
                raise RuntimeError(f"written source failed validation: {source_path}")
            expected_keys = {
                item["key"]
                for item in changes
                if item["document"] == str(source_path) and item["changed"]
            }
            by_key = {
                item.get("key"): item
                for item in records
                if item.get("key") is not None
                and float(item.get("confidence", 0.0)) >= 0.6
            }
            if any(
                by_key.get(key, {}).get("fields", {}).get(args.field) != args.value
                for key in expected_keys
            ):
                raise RuntimeError(
                    f"written field values failed verification: {source_path}"
                )
            if current.profile is not None and "index" in current.profile:
                _indexed_records, index_diagnostics = records_for_query(current)
                if "index_verified" not in {item["code"] for item in index_diagnostics}:
                    raise RuntimeError(
                        f"rebuilt index failed verification: {source_path}"
                    )
    except (OSError, RuntimeError, UnicodeDecodeError, TimeoutError) as exc:
        rollback_errors: list[str] = []
        for path in reversed(written):
            try:
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(path, original)
            except OSError as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        diagnostics.append(
            diagnostic(
                "mutation_apply_failed",
                "error",
                f"batch update failed and rollback was attempted: {exc}",
                details={"rollback_errors": rollback_errors},
            )
        )
        emit(
            {
                "schema": "mdq.mutation.v1",
                "status": "rollback_failed" if rollback_errors else "rolled_back",
                "applied": False,
                "root": str(root),
                "documents_scanned": len(paths),
                "count": len(changes),
                "change_count": change_count,
                "changes": changes,
                "documents": document_summaries,
                "diagnostics": diagnostics,
            }
        )
        return 4

    for summary in document_summaries:
        if summary["status"] == "planned":
            summary["status"] = "updated"
    emit(
        {
            "schema": "mdq.mutation.v1",
            "status": "updated" if change_count else "unchanged",
            "applied": True,
            "root": str(root),
            "documents_scanned": len(paths),
            "documents_changed": len(planned_sources),
            "indexes_rebuilt": [str(path) for path in planned_indexes],
            "count": len(changes),
            "change_count": change_count,
            "changes": changes,
            "documents": document_summaries,
            "diagnostics": diagnostics,
        }
    )
    return 0


def command_index(args: argparse.Namespace) -> int:
    document = read_document(Path(args.document))
    if document.profile is None:
        emit(
            {"status": "invalid", "written": False, "diagnostics": document.diagnostics}
        )
        return 3
    path, problem = index_path(document)
    if problem:
        emit(
            {
                "status": "invalid",
                "written": False,
                "diagnostics": list(document.diagnostics) + [problem],
            }
        )
        return 4 if problem["severity"] == "error" else 3
    assert path is not None
    records, diagnostics = extract_current(document)
    if error_diagnostics(diagnostics):
        emit({"status": "invalid", "written": False, "diagnostics": diagnostics})
        return 3
    payload = {
        "index_schema": INDEX_SCHEMA,
        "engine": ENGINE,
        "protocol_version": document.profile["version"],
        "source": str(document.path),
        "source_sha256": document.source_hash,
        "profile_sha256": document.profile_hash,
        "records": records,
        "diagnostics": diagnostics,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        diagnostics.append(
            diagnostic("index_write_failed", "error", f"could not write index: {exc}")
        )
        emit({"status": "invalid", "written": False, "diagnostics": diagnostics})
        return 4
    emit(
        {
            "status": "indexed",
            "written": True,
            "index": str(path),
            "record_count": len(
                [item for item in records if item.get("key") is not None]
            ),
            "diagnostics": diagnostics,
        }
    )
    return 0


def add_temporary_selector_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--record-level",
        type=int,
        choices=range(1, 7),
        action="append",
        help="temporary record heading level (repeatable; profileless documents only)",
    )
    parser.add_argument(
        "--key-label",
        action="append",
        help="temporary label containing the record key (repeatable)",
    )
    parser.add_argument(
        "--key-pattern",
        help="temporary safe regex used to extract a key from a heading or label",
    )
    parser.add_argument(
        "--key-group",
        help="temporary regex capture group name or number",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect, query, and safely update imperfect Markdown through a "
            "declared or temporary in-memory mdq profile."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="inspect structure and suggest a starter profile"
    )
    inspect_parser.add_argument("document")
    inspect_parser.set_defaults(handler=command_inspect)

    for name in ("validate", "diagnose"):
        validate_parser = subparsers.add_parser(
            name, help="parse current source and report recovery diagnostics"
        )
        validate_parser.add_argument("document")
        validate_parser.set_defaults(handler=command_validate)

    query_parser = subparsers.add_parser(
        "query", help="perform a trimmed, case-sensitive exact key lookup"
    )
    query_parser.add_argument("document")
    query_parser.add_argument("--id", required=True, help="exact record key")
    query_parser.add_argument(
        "--output",
        choices=("raw", "minimal", "json"),
        default="json",
        help="success output format (default: json; failures retain diagnostic JSON)",
    )
    add_temporary_selector_options(query_parser)
    query_parser.set_defaults(handler=command_query)

    run_parser = subparsers.add_parser(
        "run", help="run a reusable mdq v2 named query with quality checks"
    )
    run_parser.add_argument("document")
    run_parser.add_argument("--query", required=True, help="declared query name")
    run_parser.add_argument("--value", required=True, help="query input value")
    run_parser.set_defaults(handler=command_run)

    verify_parser = subparsers.add_parser(
        "verify", help="verify mdq v2 query intents against current record selectivity"
    )
    verify_parser.add_argument("document")
    verify_parser.set_defaults(handler=command_verify_queries)

    optimize_parser = subparsers.add_parser(
        "optimize", help="preview or apply one deterministic mdq query-contract repair"
    )
    optimize_parser.add_argument("document")
    optimize_selector = optimize_parser.add_mutually_exclusive_group(required=True)
    optimize_selector.add_argument(
        "--id", help="exact identity whose current lookup is unsatisfactory"
    )
    optimize_selector.add_argument("--query", help="declared named query to refine")
    optimize_parser.add_argument("--value", help="named-query input value")
    optimize_parser.add_argument(
        "--apply",
        action="store_true",
        help="write the verified mdq control-block patch; default is read-only preview",
    )
    optimize_parser.set_defaults(handler=command_optimize)

    search_parser = subparsers.add_parser(
        "search", help="perform a case-insensitive literal substring search"
    )
    search_parser.add_argument("document")
    search_parser.add_argument("--text", required=True)
    search_parser.add_argument("--field", help="declared field name, or key")
    search_parser.add_argument("--limit", type=int, default=20)
    add_temporary_selector_options(search_parser)
    search_parser.set_defaults(handler=command_search)

    scan_parser = subparsers.add_parser(
        "scan",
        help="query records across Markdown files or directory collections",
    )
    scan_parser.add_argument("path", nargs="+")
    scan_parser.add_argument(
        "--glob",
        action="append",
        help="directory-relative Markdown glob (repeatable; default: **/*.md)",
    )
    selectors = scan_parser.add_mutually_exclusive_group()
    selectors.add_argument(
        "--id", action="append", help="exact record key (repeatable)"
    )
    selectors.add_argument("--text", help="case-insensitive literal substring")
    scan_parser.add_argument(
        "--field",
        help="declared field to search or project, or key",
    )
    scan_parser.add_argument("--limit", type=int, default=1000)
    scan_parser.add_argument(
        "--require-contract",
        action="store_true",
        help="report every profile-free or invalid document as an error",
    )
    add_temporary_selector_options(scan_parser)
    scan_parser.set_defaults(handler=command_scan)

    set_parser = subparsers.add_parser(
        "set",
        help="preview or apply one safe scalar label-field value across a collection",
    )
    set_parser.add_argument("path", nargs="+")
    set_parser.add_argument(
        "--glob",
        action="append",
        help="directory-relative Markdown glob (repeatable; default: **/*.md)",
    )
    set_parser.add_argument(
        "--id", action="append", help="exact record key (repeatable)"
    )
    set_parser.add_argument(
        "--where",
        action="append",
        help="exact declared-field condition FIELD=VALUE (repeatable; AND semantics)",
    )
    set_parser.add_argument("--field", required=True, help="declared field to update")
    set_parser.add_argument("--value", required=True, help="new single-line text value")
    set_parser.add_argument(
        "--apply",
        action="store_true",
        help="write the validated plan; without this flag the command is read-only",
    )
    set_parser.set_defaults(handler=command_set)

    index_parser = subparsers.add_parser(
        "index", help="write the declared sidecar index from current source"
    )
    index_parser.add_argument("document")
    index_parser.set_defaults(handler=command_index)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be at least 1")
    if getattr(args, "text", None) == "":
        parser.error("--text must not be empty")
    try:
        return int(args.handler(args))
    except FileNotFoundError as exc:
        emit(
            {
                "status": "invalid",
                "diagnostics": [diagnostic("file_not_found", "error", str(exc))],
            }
        )
        return 2
    except UnicodeDecodeError as exc:
        emit(
            {
                "status": "invalid",
                "diagnostics": [
                    diagnostic(
                        "encoding_invalid", "error", f"document must be UTF-8: {exc}"
                    )
                ],
            }
        )
        return 2
    except TimeoutError:
        emit(
            {
                "status": "invalid",
                "diagnostics": [
                    diagnostic(
                        "regex_timeout",
                        "error",
                        "a profile regex exceeded the matching time limit",
                    )
                ],
            }
        )
        return 3
    except OSError as exc:
        emit(
            {
                "status": "invalid",
                "diagnostics": [diagnostic("io_error", "error", str(exc))],
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
