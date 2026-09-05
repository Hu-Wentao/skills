# mdq Semantic CLI

`mdq-semantic.py` adds local semantic candidate retrieval without changing the
existing deterministic `mdq.py` query semantics. It embeds mdq-governed record
blocks, stores vectors in a project-local derived cache, ranks candidates with
cosine similarity, and revalidates every returned record through mdq before
printing it.

## Run the CLI

The CLI is shipped inside this skill and runs through `uv`:

```bash
uv run <skill-root>/scripts/mdq-semantic.py configure \
  --project-root <project-root>
uv run <skill-root>/scripts/mdq-semantic.py index <project-root>/docs \
  --project-root <project-root>
uv run <skill-root>/scripts/mdq-semantic.py query <project-root>/docs \
  --project-root <project-root> \
  --text '仍待 Sponsor 确认的支付问题' \
  --top-k 10 \
  --where status=Open \
  --output compact
```

`configure` writes the project-local configuration to
`.mdq/semantic/config.yaml`. It never stores an API key value. Project-local
configuration may target only loopback endpoints. Configure a remote `api`
backend in the trusted user config instead:

```bash
uv run <skill-root>/scripts/mdq-semantic.py configure \
  --global --backend api --model <model> \
  --base-url https://api.example/v1 \
  --api-key-env OPENAI_API_KEY
```

The API key value is never written; export the named secret through the normal
shell or service environment. A project checkout cannot select an arbitrary
remote endpoint and environment variable together.

The first configuration must explicitly choose one of these backends:

- `ollama`: Ollama's `/api/embed` endpoint; default local endpoint is
  `http://127.0.0.1:11434` and the default model is `nomic-embed-text`.
- `omlx`: an OpenAI-compatible `/v1/embeddings` endpoint; the endpoint and
  model are configurable because local OMLX deployments may expose different
  ports or model names.
- `api`: an OpenAI-compatible `/v1/embeddings` endpoint; the API key is read
  only from the configured environment variable.

`index` accepts explicit Markdown files or directories inside the project root.
Directory scans default to `**/*.md`; use repeated `--glob` values to narrow the
scope. A normal
scoped reindex prunes deleted, filtered, or now-empty sources inside that
scope while preserving sources outside it. Only documents
with a valid persistent mdq contract are indexed. A shared Profile reference is
resolved by the normal mdq engine, so its Profile version and hash are part of
the source identity.

`query` accepts the same project-bounded file/directory scope and supports:

```text
--text QUERY             required natural-language query
--top-k N                1..100, default 10
--id ID                  repeatable exact record-key filter
--where FIELD=VALUE      repeatable exact field filter, AND semantics
--glob PATTERN           repeatable directory glob
--output json|compact    stable JSON or human-readable output
```

The result schema is `mdq.semantic.query.v1`. Each verified record includes the
record key, title, declared fields, similarity, matching text snippet, document
path, line range, UTF-8 byte range, mdq confidence, and resolved Profile source.
Semantic similarity is a ranking signal, not identity evidence.

## Cache and invalidation

The derived index defaults to:

```text
<project-root>/.mdq/semantic/index.sqlite3
```

A custom `--index` value, if used, must remain under `.mdq/semantic/` and
use the `.sqlite3` extension. Authored Markdown paths cannot be used as the
semantic cache.

The index schema is `mdq.semantic.index.v1`. It binds every source to its exact
source SHA-256, resolved Profile hash and source, backend, model, project root,
and index version. `query` returns `stale` instead of using an index when any
binding or selected-file manifest changes. Run `index` again; use `--rebuild`
after changing embedding models or backends when the complete scope should be
regenerated.

`status [path ...]` performs the same freshness check for the selected scope.
Pass the same path and `--glob` used for indexing when checking a narrowed
index.

Add `.mdq/semantic/` to the project `.gitignore`. The cache is reproducible
derived state, not an authored document or governance record.

## Safety boundary

The CLI does not provide question-answer generation in v1. It does not infer
business synonyms, approve statuses, alter Markdown, or execute `set`. It does
not treat a high similarity score as a unique identity. Duplicate, stale, or
unverifiable records are omitted or reported as diagnostics.

Use semantic results to discover likely records, then use the normal mdq
commands for exact retrieval and authorized writes:

```bash
uv run <skill-root>/scripts/mdq.py get <document.md> --id <exact-id>
uv run <skill-root>/scripts/mdq.py set <document.md> \
  --id <exact-id> --field status --value reviewed
```

Remote `api` mode is supported as a configured embedding transport, but it is
not an alternative source of truth. It must be configured globally, and source
chunks are sent to that explicitly selected service for embedding. Do not put
credentials, signed payloads, or private document material into the config,
index metadata, or diagnostic output. The local SQLite cache is created with
owner-only permissions.
