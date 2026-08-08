#!/usr/bin/env python3
"""Download known public WeChat article URLs into a collision-safe run directory."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple


DEFAULT_API_BASE = "https://down.mptext.top"
ARTICLE_HOST = "mp.weixin.qq.com"
URL_RE = re.compile(r"https?://mp\.weixin\.qq\.com/[^\s\"'<>]+", re.IGNORECASE)
TRAILING_PUNCTUATION = "\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f,.;:!?)]}>〉" 
FORMAT_SUFFIXES = {
    "markdown": ".md",
    "json": ".json",
    "text": ".txt",
    "html": ".html",
}


class DownloadError(RuntimeError):
    """A safe-to-report download failure without response-body leakage."""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def make_run_id() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha256(f"{stamp}-{time.time_ns()}".encode()).hexdigest()[:8]
    return f"{stamp}-{suffix}"


def normalize_url(value: str) -> Optional[str]:
    """Return a canonical public-article URL or None for unsupported input."""

    candidate = value.strip().strip("<>").rstrip(TRAILING_PUNCTUATION)
    if not candidate:
        return None
    try:
        parsed = urllib.parse.urlsplit(candidate)
        hostname = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or hostname != ARTICLE_HOST:
        return None
    if not parsed.path.startswith("/"):
        return None
    return urllib.parse.urlunsplit(
        ("https", ARTICLE_HOST, parsed.path, parsed.query, parsed.fragment)
    )


def extract_urls_from_text(text: str) -> List[str]:
    found: List[str] = []
    for match in URL_RE.finditer(text):
        normalized = normalize_url(match.group(0))
        if normalized:
            found.append(normalized)
    return found


def read_urls(files: Iterable[str], inline: Iterable[str]) -> List[str]:
    candidates: List[str] = []
    for item in inline:
        candidates.extend(extract_urls_from_text(item))
    for file_value in files:
        path = Path(file_value).expanduser()
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(text)
                text = json.dumps(data, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        candidates.extend(extract_urls_from_text(text))

    seen = set()
    deduped: List[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:100] or fallback


def _json_title(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key in ("title", "article_title", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for nested in value.values():
            title = _json_title(nested)
            if title:
                return title
    elif isinstance(value, list):
        for nested in value:
            title = _json_title(nested)
            if title:
                return title
    return None


def title_from_body(body: str, fmt: str, seq: int) -> str:
    if fmt == "markdown":
        for line in body.splitlines()[:40]:
            if line.lstrip().startswith("# "):
                return line.lstrip()[2:].strip()
    if fmt == "html":
        match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
        if match:
            return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    try:
        title = _json_title(json.loads(body))
    except json.JSONDecodeError:
        title = None
    return title or f"article-{seq:03d}"


def _looks_like_error(body: str, fmt: str) -> bool:
    stripped = body.strip()
    if len(stripped) < 16:
        return True
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        keys = {str(key).lower() for key in payload}
        if keys.intersection({"error", "errors", "exception"}) and not keys.intersection(
            {"title", "body", "content", "markdown", "html"}
        ):
            return True
    lowered = stripped[:600].lower()
    if fmt == "html" and "<html" not in lowered and "<!doctype" not in lowered:
        return False
    return any(marker in lowered for marker in ("access denied", "request failed", "not found"))


def _is_retryable_status(status: int) -> bool:
    return status == 408 or status == 429 or 500 <= status <= 599


def fetch_article(api_base: str, url: str, fmt: str, timeout: int, retries: int) -> str:
    query = urllib.parse.urlencode({"url": url, "format": fmt})
    endpoint = api_base.rstrip("/") + "/api/public/v1/download?" + query
    request = urllib.request.Request(
        endpoint,
        headers={
            "Accept": "text/plain, application/json, text/markdown, text/html;q=0.9",
            "User-Agent": "batch-download-wechat-data/1.0",
        },
    )
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
                if _looks_like_error(body, fmt):
                    raise DownloadError("exporter returned an empty or error payload")
                return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            if not _is_retryable_status(exc.code) or attempt >= retries:
                raise DownloadError(f"exporter HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, DownloadError) as exc:
            last_error = exc
            if isinstance(exc, DownloadError) and attempt >= retries:
                raise
            if isinstance(exc, DownloadError) and not _is_retryable_status(503):
                raise
            if attempt >= retries:
                raise DownloadError(f"exporter request failed: {exc}") from exc
        time.sleep(min(8.0, 0.8 * (2**attempt)))
    raise DownloadError(f"exporter request failed: {last_error}")


def atomic_write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(body)
    temporary.replace(path)


def unique_target(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def write_index(path: Path, rows: Sequence[dict]) -> None:
    fieldnames = [
        "seq",
        "title",
        "source_url",
        "format",
        "path",
        "status",
        "error",
        "downloaded_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download known mp.weixin.qq.com article URLs")
    parser.add_argument("urls", nargs="*", help="article URLs or text containing URLs")
    parser.add_argument("--file", action="append", default=[], help="file containing URLs; repeatable")
    parser.add_argument("--output-dir", default="", help="output directory; defaults to a fresh Downloads run")
    parser.add_argument("--format", choices=sorted(FORMAT_SUFFIXES), default="markdown")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.8, help="delay between URLs")
    parser.add_argument("--dry-run", action="store_true", help="only print normalized URLs; do not call the API")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout <= 0 or args.retries < 0 or args.sleep < 0:
        raise SystemExit("timeout must be positive; retries and sleep must be non-negative")
    try:
        urls = read_urls(args.file, args.urls)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"cannot read URL file: {exc}"}, ensure_ascii=False))
        return 2
    if not urls:
        print(json.dumps({"ok": False, "error": "no supported mp.weixin.qq.com URLs found"}, ensure_ascii=False))
        return 2
    if args.dry_run:
        print(json.dumps({"ok": True, "count": len(urls), "urls": urls}, ensure_ascii=False, indent=2))
        return 0

    run_id = make_run_id()
    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else Path.home() / "Downloads" / "wechat-mp-batch" / run_id
    )
    article_dir = output_dir / "articles"
    article_dir.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    errors: List[dict] = []
    suffix = FORMAT_SUFFIXES[args.format]

    for index, url in enumerate(urls, 1):
        seq = f"{index:03d}"
        try:
            body = fetch_article(args.api_base, url, args.format, args.timeout, args.retries)
            title = safe_name(title_from_body(body, args.format, index), f"article-{seq}")
            target = unique_target(article_dir, f"{seq}-{title}", suffix)
            atomic_write_text(target, body)
            rows.append(
                {
                    "seq": seq,
                    "title": title,
                    "source_url": url,
                    "format": args.format,
                    "path": str(target.relative_to(output_dir)),
                    "status": "success",
                    "error": "",
                    "downloaded_at": now_iso(),
                }
            )
        except Exception as exc:
            error = str(exc)
            rows.append(
                {
                    "seq": seq,
                    "title": "",
                    "source_url": url,
                    "format": args.format,
                    "path": "",
                    "status": "failed",
                    "error": error,
                    "downloaded_at": now_iso(),
                }
            )
            errors.append({"seq": seq, "source_url": url, "error": error})
        if args.sleep > 0 and index < len(urls):
            time.sleep(args.sleep)

    index_path = output_dir / "index.csv"
    errors_path = output_dir / "errors.json"
    write_index(index_path, rows)
    atomic_write_text(errors_path, json.dumps(errors, ensure_ascii=False, indent=2) + "\n")
    result = {
        "ok": not errors,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "index_csv": str(index_path),
        "errors_json": str(errors_path),
        "success_count": sum(1 for row in rows if row["status"] == "success"),
        "failure_count": len(errors),
        "failed_urls": [item["source_url"] for item in errors],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
