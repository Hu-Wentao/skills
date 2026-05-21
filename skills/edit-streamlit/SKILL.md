---
name: edit-streamlit
description: Build, debug, and refactor Streamlit apps and widgets. Use when Codex works on Streamlit UI files, session_state behavior, rerun/callback bugs, st.data_editor or dataframe widgets, layout parameters, widget keys, Streamlit version compatibility, or deprecated/new parameters such as width="stretch" replacing older container-width patterns.
---

# Streamlit

## Core Workflow

1. Inspect the installed Streamlit version and the local API signature before relying on memory:

```bash
uv run python - <<'PY'
import inspect
import streamlit as st
print(st.__version__)
print(inspect.signature(st.data_editor))
PY
```

2. Prefer the repository's package manager and app entrypoint. For Python projects using `uv`, run Streamlit through `uv run ...`.
3. Treat widget `key` values as part of the state model. Avoid changing keys casually; when a key must change to force remounting, make the remount intentional and bounded.
4. Validate with both Python checks and a running app smoke check when possible:

```bash
uv run python -m compileall path/to/file.py
uv run pytest
uv run streamlit run path/to/app.py --server.headless true --server.port <free-port>
curl -sS http://localhost:<free-port>/_stcore/health
```

## Version-Sensitive APIs

- Check local signatures for parameters that changed across Streamlit releases.
- Prefer `width="stretch"` on supported recent versions instead of older `use_container_width=True` patterns. Do not blindly convert without confirming the installed signature.
- If maintaining compatibility with older Streamlit versions, keep the compatibility choice explicit in code or in the final note. Hidden compatibility branches can mask UI bugs.
- For widget callbacks, remember that the callback runs before the script rerun completes. Use `st.session_state` as the handoff surface between the callback and the next render.

## State Rules

- Initialize session state once, then normalize existing state on later renders instead of overwriting it from the source model every rerun.
- Keep editable widget state separate from derived display data. Recompute derived columns from the editable source after every edit.
- Use stable widget keys for normal editing; use versioned keys only when a widget must be remounted to consume a freshly normalized baseline.
- Delete stale versioned widget keys after remounting to avoid accumulating obsolete state.
- When a widget returns partial state rather than full values, reconstruct the full value from a stored baseline before validating or saving.

## Complex Components

For `st.data_editor` state synchronization, derived columns, dynamic rows, and one-rerun lag bugs, read [references/data_editor.md](references/data_editor.md).

## UI Checks

- After significant Streamlit UI changes, run the app locally and hit `/_stcore/health`.
- Prefer browser verification when available for visual or interaction regressions.
- If browser automation is unavailable, report that only server-level smoke checks were performed.
