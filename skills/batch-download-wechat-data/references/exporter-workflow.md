# Exporter workflow

## Known URL body download

Use `scripts/download_urls.py` for public article URLs already supplied by the
user. It calls the configured public exporter API and writes Markdown, JSON,
text, or HTML locally. It does not fetch reading counts or comments and does
not require account login.

The default API is `https://down.mptext.top`. Treat it as an external service:
tell the user where the public URL is sent, allow an approved `--api-base`, and
do not send private or credential-bearing URLs.

## Account history

Use the upstream `wechat-article/wechat-article-exporter` when the user asks for
an account name, history list, latest N articles, or many-account export.

Typical flow:

1. Run `scripts/doctor.py --json` and confirm the exporter path.
2. Read the exporter documentation and manual gates.
3. Ask the user to scan the QR code and select the intended Official Account or
   service account.
4. Search/sync the history and save the returned JSON/chunks privately.
5. Run `scripts/analyze_history.py` before reporting totals.
6. Present scoped counts and let the user select a date range, title keyword,
   latest count, or original-only filter.
7. Download selected bodies with the exporter and validate the output index.

Never print auth-key values. Prefer environment variables or a private keychain
integration supplied by the exporter rather than writing credentials into the
skill directory.

## Enhanced metrics and comments

Use the upstream `wechat-article/wxdown-service` only when the user explicitly
asks for reading, likes, shares, favorites, comments, or replies.

The helper normally exposes a local mitmproxy port and a WSS endpoint. The user
must confirm certificate trust, any system proxy change, credential storage, and
the WeChat desktop action needed to capture fresh user-owned credentials. Start
with:

```bash
uv run --script scripts/start_metrics_service.py --dry-run
```

After credentials are available, export the metrics through the exporter and
store comments/replies as JSON sidecars. Always record whether credentials were
fresh, missing, or expired.

## Validation

Every run should leave:

- an output directory that exists;
- an index or history summary;
- a separate failed-URL/error report;
- count scopes for any history result;
- credential status for any enhanced result;
- restored system proxy state if a proxy workflow was approved.
