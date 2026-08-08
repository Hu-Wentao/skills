# Output schema

## Known URL mode

`download_urls.py` writes:

```text
<output-dir>/
├── index.csv
├── errors.json
└── articles/
    ├── 001-title.md
    └── 002-title.md
```

`index.csv` contains:

```text
seq,title,source_url,format,path,status,error,downloaded_at
```

`errors.json` contains only failed URL records. A non-zero exit code means at
least one requested URL failed.

## Enhanced archive

Keep one row per article with these fields where available:

```text
account_name, fakeid, title, url, publish_time, author, digest, cover_url,
body_markdown_path, html_path, image_dir, read_count, like_count, share_count,
favorite_count, comment_count, comments_path, comment_replies_path, fetch_mode,
credential_status, exported_at, error
```

Store comments and replies as sidecar JSON files. Do not put raw cookies,
auth-key, `pass_ticket`, keys, tokens, `uin`, or credentials JSON in the
archive.

## History count fields

`analyze_history.py` writes `history.summary.json`, `history.summary.md`,
deduplicated JSON/CSV, original-only JSON/CSV, and all/original URL lists.

- `expanded_url_items`: unique article URLs after expanding multi-article
  messages;
- `publish_groups`: unique `msgid` values, roughly one publish/message group;
- `headline_items`: rows with `itemidx=1`;
- `original_articles`: `copyright_type=1`, `copyright_stat=1`, and
  `is_deleted=false`;
- `deleted_items`: rows marked deleted;
- `duplicate_records_removed`: records removed during normalization.

Do not call `expanded_url_items` “original articles” or compare it directly to
the count shown by a WeChat frontend without explaining the scope.
