---
name: recall-resources
description: Capture, assess, and recall a personal library of open-source projects, workflows, articles, webpages, tools, and knowledge through hybrid lexical and local-embedding search. Use when the user asks to save or capture a discovered resource or article, including a public WeChat article URL; when project governance needs a shared upstream open-source assessment; or before recommending or selecting third-party services, integrations, payment providers, libraries, implementation workflows, research approaches, or other reusable external resources that may have a previously saved match.
---

# Recall Resources

Use the bundled wrapper so the command works from any project:

```bash
uv run --script "$SKILL_DIR/scripts/recall.py" <command> [arguments]
```

The wrapper resolves the source checkout from `RESOURCE_MEMORY_SOURCE`, its own
Git checkout, or the managed skill-source registry. `RESOURCE_MEMORY_HOME` may
point to a separate authored data root; otherwise the source checkout is also
the data root.

## Capability Contract

Before another skill relies on shared storage, run:

```bash
uv run --script "$SKILL_DIR/scripts/recall.py" capabilities --json
```

Require schema `resource-memory.capabilities.v1` and
`capabilities.shared_open_source_assessment.version >= 1`. Skill installation
or folder presence alone is not capability evidence. If capability detection
fails, the caller must use its documented local fallback and must not partially
write a cross-project record.

## Optional article acquisition backend

Load this backend only when the user is capturing an article-like URL and the
article body is not already available. It is a capability of this skill, not a
separate auto-triggered skill.

- Prefer `wechatsync.extract_article` for the visible current page, then use
  the browser's identified article container as the read-only fallback.
- For a public `mp.weixin.qq.com` URL, if the connector/browser path is
  unavailable or blocked, read
  `references/wechat-data/exporter-workflow.md` and use the known-URL scripts
  under `scripts/wechat_data/`. This path can download one or many public URLs
  as Markdown, JSON, text, or HTML without WeChat login.
- Use the history mode only when the user asks for a public account's history,
  latest articles, date/title filtering, or original-article counts.
- Use the enhanced mode only when the user explicitly asks for reading,
  likes, shares, favorites, comments, or replies. Read
  `references/wechat-data/manual-gates.md` before any credential, certificate,
  proxy, or WeChat desktop step.
- Validate the downloaded body before calling `add` or `archive`. Preserve
  failed URLs separately and never create a link-only record after an
  acquisition failure.

The known-URL backend sends the public URL to its configured exporter API,
defaulting to `https://down.mptext.top`. Tell the user when this external
service is used and never send private or credential-bearing URLs.

## Recall

1. Translate the current task into a short search query containing the goal and material
   constraints, not a guessed product name alone.
2. Run:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" search \
     "<goal and constraints>" --ensure-index --load-model --json
   ```

3. Inspect the returned source URL, review status, use cases, and constraints. Open authored
   notes or sources only when needed for the current decision.
4. Recommend a result only when it fits the current project. Explain why it is related and
   preserve every recorded caveat. Treat `unverified` or stale material as a lead to recheck,
   never as current policy or proof.
5. If no relevant result exists, continue the task normally and say nothing about the empty
   search unless it affects the user's decision.

## Capture

1. Capture only facts supplied by the user or visible in the source. Do not invent a URL,
   summary, applicability, or verification state.
2. Classify the source before writing. For article-like web pages, including
   WeChat articles and ordinary blog pages, use the Article branch below. Use
   the generic branch only for non-article resources such as projects, tools,
   or reference pages.
3. For non-article tool or website resources, perform only one focused reachability check:
   use a direct browser navigation or an HTTP check and record only whether the request
   reached the site. Do not inspect page text, DOM, metadata, features, or other contents.
   Treat browser/network policy blocks as an unverified check, not as proof that the site
   is unavailable. Do not replace a blocked check with a search result or content review.
4. Describe the reusable problem in `--summary`, task signals in repeated `--use-when`, and
   limitations in repeated `--constraint` values.
5. Default new external material to `unverified` unless it was actually checked against an
   authoritative source.
6. Generic branch: add one metadata record, then rebuild its derived index:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" add \
     --title "<title>" --type "<type>" --url "<url>" \
     --summary "<reusable value>" --use-when "<task signal>"

   uv run --script "$SKILL_DIR/scripts/recall.py" index --load-model
   ```

   Omit `--url`, `--constraint`, or `--concept` when unknown. Never write placeholders.

### Article Branch

For an article-like web page, a URL-only record is incomplete. Do not create a
new record until the article body has been captured, unless repairing an
existing URL-only record.

1. Open the URL in the browser and use the purpose-built
   `wechatsync.extract_article` connector to obtain the visible title,
   author/date metadata, and article body. Use this same connector for both
   WeChat and ordinary blog pages. If the connector is unavailable, use the
   browser's visible article container as the read-only fallback (for example
   `#js_content`, `article`, `main`, or the site's clearly identified content
   container). If the URL is a public `mp.weixin.qq.com` page and both browser
   paths are unavailable, use the optional known-URL backend described above.
   Never substitute a search result or an invented summary.
2. Save the extracted body as UTF-8 Markdown (or the returned HTML when Markdown is not
   available) in a temporary file. Preserve the body; do not reduce it to the summary.
   Validate that the result contains article text and is not a connector error, browser
   security message, login page, or empty placeholder. On any such failure, stop before
   `add`/`archive` and leave the source unchanged.
3. Add the metadata record with `--type article`, then immediately persist the body with:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" archive \
     --resource-id "<returned-resource-id>" \
     --content-file "<temporary-content-file>" \
     --format markdown \
     --author "<visible-author>" \
     --published-at "<visible-published-time>"
   ```

   The archive command writes `resources/archives/<resource-id>.md` and links it from the
   catalog's `Archive` field. It is idempotent for identical content and refuses to
   overwrite changed content without `--replace`.
4. Only after the archive succeeds, run `index --load-model`. The archived body is included
   in lexical and semantic search. If extraction fails, do not leave a new link-only
   record; report the failure and keep the source unchanged.
5. When repairing an existing URL-only record, resolve its exact ID first:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" show \
     --url "<article URL>" --json
   ```

   Then run `archive` against that ID and rebuild the index. Do not change the existing
   resource ID.

## Share an Open-Source Assessment

Use this workflow when an authorized evaluation of an open-source project is
generally reusable across projects.

1. Normalize identity by repository URL and inspect an existing record first:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" evaluation get \
     --url "<repository URL>" --json
   ```

   A not-found result is expected for a first assessment.
2. Prepare one JSON object with `title`, `source_url`, exact `upstream_ref`,
   `evaluated`, `summary`, and at least one `evidence` item. Optional arrays are
   `capabilities`, `architecture`, `compatibility`, `maintenance`, `security`,
   `strengths`, `risks`, and `review_triggers`. `status` defaults to `current`.
3. Keep only upstream/general evidence in this object. Never include current
   project fit, project constraints, integration cost, disposition, or an
   adopt/reject decision.
4. Upsert the prepared JSON and capture the returned stable ID and revision:

   ```bash
   uv run --script "$SKILL_DIR/scripts/recall.py" evaluation upsert \
     --input <assessment.json> --json
   ```

5. Rebuild the derived index when immediate semantic discovery is required.
   The shared assessment is automatically included in subsequent hybrid index
   builds.

The returned `revision` is the `sha256` of the exact authoritative Markdown
bytes. A consuming project must pin that value with the shared assessment ID
and upstream ref; a later shared update never rewrites or silently changes the
project's historical fit conclusion.

## Safety

- Keep Markdown authoritative; never edit the SQLite cache directly.
- Treat `evaluations/*.md` as shared upstream evidence and the consuming
  project's `TECH-FIT-*` record as project-specific decision support.
- Do not treat structural validation or vector similarity as semantic truth.
- Do not change an existing resource ID. Add a superseding record or update content through an
  explicitly authorized catalog edit.
- Do not install, adopt, contact, purchase, publish, or configure a recalled resource without
  separate task authority.
