---
name: release-flutter-web-s3
description: Prepare, build, and publish a Flutter Web app to S3-compatible object storage. Use when Codex needs to bump or update pubspec.yaml version, create a Flutter Web release tag, configure a reusable S3 deployment script, build build/web, upload or promote web assets, or inspect a Flutter Web S3 release workflow.
---

# Release Flutter Web S3

## Scope

Use this skill from the root of a Flutter application repository that publishes its Web build to AWS S3 or an S3-compatible object storage provider such as Cloudflare R2, MinIO, Tigris, Backblaze B2, or DigitalOcean Spaces.

Default assumptions:

- Version source: `pubspec.yaml`
- Build output: `build/web`
- Release helper: this skill's `scripts/prepare_web_release.py`
- Deploy script template: this skill's `scripts/release_web_s3.sh`, usually copied into the project as `scripts/release_web_s3.sh`
- Local deploy config: `deploy/s3.env`, ignored by git
- Default tag pattern: `web-v<pubspec version>`
- Package manager/runtime preference: `uv` for Python helpers, `fvm` when the project uses FVM

Adapt these defaults to the target project before publishing. Do not assume the project has Slang, a specific GitHub Actions workflow, or a specific object storage provider.

Do not print secret values from `deploy/s3.env` or GitHub secrets. Any compatibility switch such as `BUILD_WASM`, `S3_ADDRESSING_STYLE`, `AWS_REQUEST_CHECKSUM_CALCULATION`, `AWS_RESPONSE_CHECKSUM_VALIDATION`, or `ALLOW_DIRTY` must be explicitly called out before use because these can hide provider or runtime differences.

## Workflow

### 1. Preflight

Verify repository state before changing files:

```bash
git status --short
git branch --show-current
git status -uno
```

If unrelated uncommitted changes exist, stop and ask whether to commit them first or ignore them for this release. If the branch is behind its upstream, pull or ask the user how to proceed before releasing.

Confirm the Flutter app shape:

```bash
test -f pubspec.yaml
test -d lib
test -d web
```

Detect command style:

- If `.fvm/fvm_config.json`, `.fvmrc`, or `.fvm` exists, run Flutter and Dart commands through `fvm`.
- Otherwise use the project's normal `flutter` and `dart` commands.
- If the project uses generated code, inspect `pubspec.yaml`, `build.yaml`, `slang.yaml`, `melos.yaml`, and existing CI before choosing generation commands.

### 2. Install Or Review The Deploy Script

If the project already has a web deploy script, inspect it and preserve its project-specific behavior unless it is wrong. If the project does not have one, copy this skill's template into the app:

```bash
mkdir -p scripts deploy
cp .codex/skills/release-flutter-web-s3/scripts/release_web_s3.sh scripts/release_web_s3.sh
chmod +x scripts/release_web_s3.sh
```

Adjust the source path if skills are installed somewhere other than `.codex/skills`.

If the user needs local AWS CLI credentials setup, point them to `references/awscli-setup.md` in this skill before asking them to run upload commands. Prefer a named profile over exporting long-lived access keys into the shell.

Create `deploy/s3.env.example` with non-secret placeholders, then create a local `deploy/s3.env` from it and ensure `deploy/s3.env` is git-ignored. Keep secrets out of commits:

```dotenv
S3_ENDPOINT_URL=https://s3.example.com
S3_BUCKET=my-bucket
S3_REGION=auto
S3_LIVE_PREFIX=web
S3_RELEASE_PREFIX=web/releases
BASE_HREF=/
PWA_STRATEGY=none
```

Required runtime configuration:

- `S3_ENDPOINT_URL`: provider endpoint URL
- `S3_BUCKET`: target bucket
- credentials via `AWS_PROFILE`, CI secrets, or the provider's supported AWS CLI mechanism; direct `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` may fail on some S3-compatible providers
- for local uploads, prefer configuring a named AWS CLI profile with `aws configure --profile <new-profile-name>` and setting `AWS_PROFILE=<profile>` so the script appends `aws --profile <profile>` consistently

Optional project configuration:

- `BASE_HREF`: set this to `/subpath/` when the app is hosted below the domain root
- `PWA_STRATEGY`: passed to `flutter build web --pwa-strategy`
- `BUILD_WEB_DIR`: override when the web output is not `build/web`
- `BUILD_WASM=1`: add `--wasm`, only after browser/runtime compatibility is verified
- `FLUTTER_CMD`, `DART_CMD`, `PRE_BUILD_CMD`, `TEST_CMD`, `BUILD_RUNNER_CMD`, `SLANG_CMD`: override command discovery for non-standard projects

### 3. Choose The Version

Run the helper to inspect the current version, last `web-v*` tag, commits since that tag, suggested SemVer bump, tag name, and draft release notes:

```bash
uv run python .codex/skills/release-flutter-web-s3/scripts/prepare_web_release.py
```

The helper treats breaking commits as major, `feat` commits as minor, `fix` or `perf` commits as patch, and other changed commits as patch. If the project uses another tag prefix, pass it explicitly:

```bash
uv run python .codex/skills/release-flutter-web-s3/scripts/prepare_web_release.py --tag-match "release-web-*" --tag-prefix "release-web-"
```

If the user provides a version, use it instead of the suggestion:

```bash
uv run python .codex/skills/release-flutter-web-s3/scripts/prepare_web_release.py --version 0.1.0 --write
```

When the chosen version is final, write it to `pubspec.yaml`:

```bash
uv run python .codex/skills/release-flutter-web-s3/scripts/prepare_web_release.py --version <version> --write
```

### 4. Validate Before Publishing

Run the same commands the release script depends on, or let the release script run them. Use `fvm` only when the project uses FVM:

```bash
fvm flutter pub get
fvm flutter test
```

If the project has code generation, run the existing project command, for example:

```bash
fvm dart run build_runner build -d
fvm dart run slang
```

For an upload rehearsal, use dry-run mode. This still requires object storage configuration, but does not change objects:

```bash
scripts/release_web_s3.sh --dry-run
```

If generated files or the version change need committing for a reproducible release, commit before uploading or tagging:

```bash
git add pubspec.yaml
git commit -m "chore(release): web <version>"
```

### 5. Publish

For a local publish to the configured object storage bucket:

```bash
scripts/release_web_s3.sh
```

For a CI-driven publish, create and push a tag that matches the project's workflow:

```bash
git tag web-v<version>
git push
git push origin web-v<version>
```

Keep `pubspec.yaml` version, `RELEASE_ID`, and the tag version aligned unless the project intentionally separates app version from deploy release ID. If a workflow strips `web-v` and passes the rest as `RELEASE_ID`, verify that behavior before tagging.

### 6. Promote An Existing Release

Promote without rebuilding only when the immutable release already exists in object storage:

```bash
scripts/release_web_s3.sh --promote-only <release-id>
```

Use `--dry-run` first when changing prefixes or provider configuration:

```bash
scripts/release_web_s3.sh --promote-only <release-id> --dry-run
```

Promotion copies an immutable release prefix to the live prefix. Use it for rollback or staged promotion, and confirm the release ID and prefixes before running without `--dry-run`.

## Resources

### scripts/

- `prepare_web_release.py`: inspect commits since the latest `web-v*` tag, suggest a SemVer version, generate `web-v<version>`, draft release notes, and optionally update `pubspec.yaml`.
- `release_web_s3.sh`: reusable project script template for building Flutter Web, writing `version.json`, syncing an immutable release prefix, refreshing live assets, and promoting an existing release.
- `references/awscli-setup.md`: local setup guide for installing AWS CLI, obtaining `ak/sk`, creating a named profile, and using that profile with `release_web_s3.sh`.
