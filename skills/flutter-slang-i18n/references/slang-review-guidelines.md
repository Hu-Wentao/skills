# Slang Review Guidelines

## Hardcoded string triage

Localize strings when they are visible or announced to the user:

- Widget text: `Text`, `SelectableText`, `TextSpan`, `RichText`, button labels, tab labels.
- Form copy: `labelText`, `hintText`, `helperText`, `errorText`, validator return values.
- Feedback: snackbars, dialogs, banners, toasts, empty states, loading states, user-facing exceptions.
- Navigation: app bar titles, page titles, menu items, bottom navigation labels.
- Accessibility: `Semantics.label`, `tooltip`, icon button tooltips.

Usually keep strings hardcoded when they are not product copy:

- Import/export URIs, package names, route paths, asset paths, file names.
- Analytics event names, log tags, debug labels, storage keys, test fixture values.
- API constants, protocol values, enum names, JSON keys, feature flags.
- `Key`, `ValueKey`, `ObjectKey`, `PageStorageKey`, restoration IDs, hero tags.

When unsure, inspect the call site and the data flow. A string inside `Text()` is usually UI. A string passed into a repository, API client, logger, or persistence layer usually is not.

## Regex searches worth running

Use these after running the scanner, because they catch framework patterns the scanner may score too low:

```bash
rg -n --glob 'lib/**/*.dart' "(Text|SelectableText|TextSpan)\s*\(\s*r?['\"]"
rg -n --glob 'lib/**/*.dart' "(labelText|hintText|helperText|errorText|tooltip|semanticLabel)\s*:\s*r?['\"]"
rg -n --glob 'lib/**/*.dart' "(SnackBar|AlertDialog|SimpleDialog|showDialog|showModalBottomSheet)"
rg -n --glob 'lib/**/*.dart' "validator\s*:\s*\([^)]*\)\s*\{"
rg -n --glob 'lib/**/*.dart' "\b(context\.)?[tS]\.|Translations\.of\(context\)"
```

## Semantic key rules

Name keys by UI intent and scope:

- Prefer `auth.login.submitButton`, `profile.emptyState.title`, `checkout.cardDeclined.message`.
- Avoid `screen.title` when a screen has multiple titles. Use the component or state: `settings.accountSection.title`.
- Avoid English-as-key names such as `continueText` when the concept is stronger: `onboarding.nextButton`.
- Avoid generic shared keys unless the action and tone are identical everywhere. `common.cancel` is fine; `common.done` is risky if it means submit, dismiss, finish setup, or close.
- Keep validation and error keys close to the domain: `signup.email.invalidFormat`, not `errors.invalid`.
- If copy changes from "Sign in" to "Continue", keep the key if the intent stays login submission. Rename when the UI intent changes.

## Slang usage checks

- In widgets, prefer `final S = Translations.of(context)` when the project uses `translate_var: S`, or follow the project's context extension style so widgets rebuild on locale changes.
- Outside widget build context, `S.some.key` is acceptable for non-reactive usage when `translate_var: S` is configured.
- Use parameters for dynamic values instead of string concatenation.
- Use pluralization for counts and context/gender support where grammar requires it.
- Keep all locale files structurally aligned before running generation.

## Review output

For each change, record:

- The original hardcoded string and file location.
- Whether it was localized or intentionally skipped.
- The new or reused key.
- Any key rename and why the rename is behaviorally safe.
- Any compatibility bridge added for renamed keys. Do not add one silently.
