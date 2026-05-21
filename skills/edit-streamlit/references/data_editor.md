# st.data_editor Patterns

Use this reference when `st.data_editor` appears to lag by one edit, has dynamic rows, uses derived/read-only columns, or needs robust callback synchronization.

## Mental Model

`st.data_editor` returns a fully edited data object from the current render, but its `st.session_state[key]` widget state stores a patch-like structure:

```python
{
    "edited_rows": {0: {"column": value}},
    "added_rows": [{"column": value}],
    "deleted_rows": [2],
}
```

Callbacks run before the rerun finishes. If the next render rebuilds the table from the old model object instead of a session draft, the UI can appear one edit behind.

## Robust Callback Pattern

Use this pattern when the table has computed columns, sorted display order, or dynamic row additions/deletions.

1. Store a draft `DataFrame` in `st.session_state`.
2. Before rendering, normalize the draft and store a `base_frame` snapshot for the editor.
3. In `on_change`, read `st.session_state[editor_key]`, apply `edited_rows`, `deleted_rows`, and `added_rows` to `base_frame`.
4. Recompute derived columns in the callback.
5. Increment an `editor_version` and include it in the editor key to force a clean remount.
6. Delete stale versioned editor keys so `added_rows` is not applied again on future edits.

## Minimal Skeleton

```python
def apply_editor_state(base_frame, editor_state):
    edited = base_frame.copy().reset_index(drop=True)

    for row_index, changes in editor_state.get("edited_rows", {}).items():
        for column_name, value in changes.items():
            edited.at[int(row_index), column_name] = value

    deleted = [int(i) for i in editor_state.get("deleted_rows", [])]
    if deleted:
        edited = edited.drop(edited.index[deleted])

    added = editor_state.get("added_rows", [])
    if added:
        edited = pd.concat([edited, pd.DataFrame(added)], ignore_index=True)

    return normalize_editor_frame(edited)


def sync_editor_state(editor_key, base_key, draft_key, version_key):
    base = st.session_state.get(base_key)
    state = st.session_state.get(editor_key)
    if base is None or state is None:
        return
    st.session_state[draft_key] = apply_editor_state(pd.DataFrame(base), dict(state))
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


draft_key = "points.draft"
base_key = "points.base"
version_key = "points.version"

if draft_key not in st.session_state:
    st.session_state[draft_key] = initial_frame
else:
    st.session_state[draft_key] = normalize_editor_frame(
        pd.DataFrame(st.session_state[draft_key])
    )

frame = pd.DataFrame(st.session_state[draft_key])
st.session_state[base_key] = frame.copy()

version = int(st.session_state.setdefault(version_key, 0))
editor_key_prefix = "points.editor."
editor_key = f"{editor_key_prefix}{version}"
for key in list(st.session_state.keys()):
    if key.startswith(editor_key_prefix) and key != editor_key:
        del st.session_state[key]

edited = st.data_editor(
    frame,
    key=editor_key,
    on_change=sync_editor_state,
    args=(editor_key, base_key, draft_key, version_key),
    num_rows="dynamic",
    width="stretch",
)
```

## Derived Columns

When some columns are computed from editable columns:

- Disable computed columns in `column_config` and `disabled=[...]`.
- Recompute them in the normalizer, not after validation only.
- Use the normalized draft as the next editor input.
- Avoid using the returned `edited` frame as the only source of truth when an `on_change` callback is also managing state.

## Sorting and Config Order

Display order and persistence order may differ. For example, a trading UI can display price lines from high to low while the config model requires `z` from low to high.

- Sort the draft for user display.
- Convert to the model-required order immediately before validation or save.
- Make the conversion explicit in code and final notes; do not hide it as a compatibility tweak.

## Dynamic Rows

`added_rows` is patch state. If the same editor key is reused after applying additions to a draft frame, Streamlit can reapply the old addition. Version the key after callback sync when dynamic rows are enabled.

## Validation

Validate both the UI draft and the model output:

- UI draft: missing values, duplicate keys, invalid ranges, display sort.
- Model output: required row count, type conversion, model-specific ordering.
- If the draft is invalid, keep rendering the draft but fall back to the last valid model values for downstream expensive operations.
