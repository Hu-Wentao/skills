---
name: batch-download-wechat-data
description: "Download and normalize WeChat Official Account data through three explicit modes: known article URLs to Markdown/JSON/text/HTML, account history export with scoped counts, and enhanced read/like/share/favorite/comment data. Use when the user asks to batch download mp.weixin.qq.com articles, export a public account history, analyze original-article counts, or collect article interaction metrics. Do not use it to operate WeChat UI, publish content, or bypass login, private access, deleted content, paywalls, or platform permissions."
---

# Batch Download WeChat Data

Use this skill as an independent three-mode workflow. Keep the modes separate so
an ordinary public URL never triggers a login, proxy, certificate, or credential
flow.

## Mode selection

1. **Known URLs** — use when the user supplies one or more public
   `mp.weixin.qq.com` URLs and wants article bodies. Use
   `scripts/download_urls.py`; this path does not need WeChat login.
2. **Account history** — use when the user wants an account's history, latest N
   articles, original-only articles, or a date/title-filtered export. Use the
   upstream `wechat-article-exporter` workflow, then run
   `scripts/analyze_history.py` before reporting counts.
3. **Enhanced data** — use when the user explicitly asks for reading, likes,
   shares, favorites, comments, or replies. Read the manual gates first, obtain
   confirmation for credential capture, certificates, proxy changes, or WeChat
   desktop actions, then use `wxdown-service` with the exporter.

Do not silently combine modes. If the request is ambiguous, start with the
least-privileged known-URL mode and state what it cannot provide.

## Common rules

- Run the read-only environment check before choosing a non-trivial workflow:
  `uv run --script scripts/doctor.py --json`.
- Never operate the user's WeChat UI, scan a QR code, choose an account, send
  messages, publish, delete, follow, or unfollow on the user's behalf.
- Never print or save cookies, auth-key, tokens, `pass_ticket`, `uin`, QR
  secrets, or credential JSON in chat or the output archive.
- The known-URL mode sends public article URLs to the configured exporter API
  (default `https://down.mptext.top`). Tell the user when this external
  service is being used and allow `--api-base` to point to an approved service.
- Do not fetch private URLs or use another person's account/session. Respect
  copyright and keep downloaded material within the user's lawful use.
- Preserve failed URLs separately. A partial run is not a complete run.

## Known-URL mode

Run one URL:

```bash
uv run --script scripts/download_urls.py \
  "https://mp.weixin.qq.com/s/..." --format markdown
```

Run a URL list from text, CSV, or JSON:

```bash
uv run --script scripts/download_urls.py \
  --file urls.txt --format markdown --output-dir ./wechat-export
```

The script validates the host, deduplicates URLs, retries transient HTTP
failures with bounded backoff, rejects obvious error payloads, writes UTF-8
content atomically, and produces `index.csv` plus `errors.json`. Its default
output is a fresh run directory under `~/Downloads/wechat-mp-batch/`; it never
recursively deletes or resets an existing directory.

Report the success count, failure count, failed URLs, output directory, and
`index.csv`. Inspect a sample article before archiving it into another system.

## Account-history mode

Read [references/exporter-workflow.md](references/exporter-workflow.md) before
using account history. The upstream exporter requires a user-owned Official
Account or service-account login for history APIs. Ask the user to perform QR
login and account selection. Do not report a single undifferentiated article
count. Use these scopes:

- `publish_groups`: unique `msgid` values, roughly one publish/message group;
- `expanded_url_items`: unique article URLs after expanding multi-article
  messages;
- `original_articles`: `copyright_type=1`, `copyright_stat=1`, and
  `is_deleted=false`.

After history JSON or chunk files are available, run:

```bash
uv run --script scripts/analyze_history.py \
  --history-json /path/to/history.json --output-dir /path/to/analysis
```

Validate that the output contains the summary JSON/Markdown, deduplicated JSON/
CSV, and all/original URL lists. Explain count-scope differences before
comparing them with numbers shown in WeChat.

## Enhanced-data mode

Read [references/manual-gates.md](references/manual-gates.md) and obtain the
user's explicit confirmation before installing dependencies, trusting a local
mitmproxy certificate, changing system proxy settings, starting a traffic
interceptor, or storing credentials. Use
`scripts/start_metrics_service.py --dry-run` to inspect the command first; the
wrapper itself does not change system proxy settings. Fresh user-owned
credentials are required for metrics and comments, and expired credentials or
hidden/disabled comments must be reported as limitations.

## Output contract

Read [references/output-schema.md](references/output-schema.md) when merging
body, history, metrics, or comments. Keep one row per article and retain
`source_url`, `fetch_mode`, `credential_status`, timestamps, and error fields.
Store comments and replies as sidecar JSON files instead of embedding large raw
comment bodies in chat.

## Bundled scripts

- `scripts/download_urls.py`: public known-URL downloader.
- `scripts/doctor.py`: read-only environment and network check.
- `scripts/analyze_history.py`: normalize, deduplicate, count, and export
  history records.
- `scripts/start_metrics_service.py`: explicit, dry-run-first local helper
  launcher for enhanced-data workflows.
- `scripts/tests/run.py`: dependency-free regression checks for the bundled
  scripts.
