---
name: flutter-slang-i18n
description: Add and maintain Slang localization in Flutter projects. Use when Codex needs to introduce slang, slang_flutter, or slang_build_runner, migrate hardcoded Flutter UI strings into Slang translations, scan Dart code for user-visible strings, or review existing Slang keys for semantic fit.
---

# Flutter Slang I18n

## Workflow

1. Check project state before edits.
   - Run `git status --short` and follow the repository's change-safety policy before modifying files.
   - Find the Flutter package root containing `pubspec.yaml`.
   - If `.fvm/fvm_config.json` exists, run Flutter and Dart commands through `fvm`.
   - Inspect existing localization (`slang.yaml`, `build.yaml`, `lib/i18n`, `intl`, ARB, `easy_localization`) before adding another system. If replacing an existing i18n stack, call out migration risk first.

2. Add Slang using current package names.
   - Prefer the official packages `slang`, `slang_flutter`, and, when using build_runner, `slang_build_runner` plus `build_runner`.
   - If a request mentions `flutter_slang`, verify the package name before using it; Slang's Flutter support package is normally `slang_flutter`.
   - Use the project command style:
     ```bash
     fvm flutter pub add slang slang_flutter
     fvm flutter pub add flutter_localizations --sdk=flutter
     fvm flutter pub add -d build_runner slang_build_runner
     ```
     Drop `fvm` only when the project is not using FVM.
   - Add a base translation file such as `lib/i18n/en.i18n.json` and a peer locale such as `lib/i18n/zh-CN.i18n.json` when the product supports Chinese.
   - Use `slang.yaml` for `fvm dart run slang`; use `build.yaml` for build_runner integration. Keep the generated output path consistent with the existing project style.
   - When creating a new Slang config, set `translate_var: S` instead of Slang's default `t`:
     ```yaml
     translate_var: S
     ```
     For build_runner, put the same option under `targets.$default.builders.slang_build_runner.options`.
   - If an existing project already uses the generated `t` variable, changing `translate_var` to `S` is a breaking source change. Tell the user explicitly, then update every `t.<key>` call site or keep the existing variable name if the user does not want that break.
   - Generate code with `fvm dart run slang` or `fvm dart run build_runner build -d`, matching the chosen setup.

3. Wire Flutter integration.
   - Import the generated file, usually `package:<app>/i18n/translations.g.dart`.
   - Initialize locale handling in `main`, for example `LocaleSettings.useDeviceLocale()`.
   - Wrap the app with `TranslationProvider` when using Slang locale handling.
   - Set `MaterialApp.locale`, `supportedLocales`, and `localizationsDelegates` so Flutter framework strings also localize.
   - In widgets that must rebuild on locale changes, prefer `final S = Translations.of(context)` or the project's context extension style.

4. Scan hardcoded strings, then confirm by context.
   - Run `scripts/scan_dart_strings.py` from this skill against the target Flutter project:
     ```bash
     uv run python /path/to/flutter-slang-i18n/scripts/scan_dart_strings.py --root /path/to/flutter/project
     ```
     If the target environment does not use `uv`, run the executable script directly.
   - Treat scanner output as candidates, not truth. Review surrounding code before changing anything.
   - Localize user-visible UI strings: `Text`, labels, hints, tooltips, dialogs, snackbars, validation messages, empty states, errors shown to users, semantics labels, and accessibility copy.
   - Usually skip non-UI strings: imports, asset paths, route paths, analytics event names, log/debug messages, test fixtures, protocol values, enum names, storage keys, and `Key` or `ValueKey` values.

5. Replace strings with semantic Slang keys.
   - Add keys that describe product/UI intent, not only the current English words.
   - Preserve interpolation and formatting with Slang parameters, pluralization, and contexts when applicable.
   - Keep shared keys only for identical meaning across contexts. Do not reuse a key just because two English strings currently match.
   - Update all locale files together. If a translation is unknown, add a clear placeholder consistent with the repo's localization policy and flag it in the final response.

6. Audit existing Slang usage.
   - Find generated translation use:
     ```bash
     rg -n "\b(context\.)?[tS]\.|Translations\.of\(context\)" lib
     ```
   - Compare each key path with the surrounding UI. Rename keys like `title`, `text1`, `ok`, or stale copied feature names when they no longer describe the UI intent.
   - Key renames break source references and translation files. State this explicitly, update every call site and locale, and avoid hidden compatibility aliases unless the user agrees.
   - Read `references/slang-review-guidelines.md` for key naming and triage rules when the audit is non-trivial.

7. Validate.
   - Run code generation after translation changes.
   - Run `fvm dart run slang analyze` when Slang CLI is configured, and fix missing or unused translations relevant to the change.
   - Run `fvm dart format` on changed Dart files.
   - Run the narrowest useful checks: generated i18n compile test, widget tests around changed screens, or `fvm flutter test` when the change spans shared UI.
   - Report scan limitations and any strings intentionally left hardcoded.

## Resources

- `scripts/scan_dart_strings.py`: Regex/lexer-based Dart scanner for likely hardcoded UI strings.
- `references/slang-review-guidelines.md`: Triage rules for hardcoded strings and semantic Slang key review.
