---
name: release-flutter-web-s3
description: Prepare, build, and publish a Flutter Web app to S3-compatible object storage. Use when Codex needs to bump or update pubspec.yaml version, create a Flutter Web release tag, configure S3 deployment, build build/web, upload or promote web assets, or inspect a Flutter Web S3 release workflow.
---

# Release Flutter Web S3

## Scope

Use this skill from the root of a Flutter application repository that publishes its Web build to AWS S3 or an S3-compatible object storage provider such as Cloudflare R2, MinIO, Tigris, Backblaze B2, or DigitalOcean Spaces.

Default assumptions:

- Version source: `pubspec.yaml`
- Build output: `build/web`
- Main entry point: this skill's `scripts/release_web_s3.py`
- Version helper: this skill's `scripts/prepare_web_release.py`
- Local deploy config: `deploy/s3.env`, ignored by git
- Default tag pattern: `web-v<pubspec version>`
- Package manager/runtime preference: `uv` for Python helpers, `fvm` when the project uses FVM

Adapt these defaults to the target project before publishing. Do not assume the project has Slang, a specific GitHub Actions workflow, or a specific object storage provider.

Do not print secret values from `deploy/s3.env` or GitHub secrets. Any compatibility switch such as `BUILD_WASM`, `S3_ADDRESSING_STYLE`, `AWS_REQUEST_CHECKSUM_CALCULATION`, `AWS_RESPONSE_CHECKSUM_VALIDATION`, or `ALLOW_DIRTY` must be explicitly called out before use because these can hide provider or runtime differences.

## Main Usage

Use `scripts/release_web_s3.py` as the only release entry point.

### Parameters

- `--project-root`: manually specify the Flutter project root; by default the script auto-detects it from git or `pubspec.yaml`
- `--pubspec`: override the `pubspec.yaml` path relative to the project root
- `--tag-match`: specify the git tag glob used to locate the previous Web release; default `web-v*`
- `--tag-prefix`: specify the git tag prefix for the new release; default `web-v`
- `--version`: explicitly set the release version and bypass the suggested version
- `--bump {major|minor|patch}`: override the detected semantic version bump
- `--dry-run`: print planned file, git, build, and S3 actions without making changes
- `--skip-tests`: skip the Flutter test step during validation
- `--no-tag`: do not create the git release tag after publishing
- `--no-push`: do not push the git release tag to remote
- `--yes` / `-y`: non-interactive mode; fail instead of prompting for confirmation
- `--promote <release-id>`: skip version/build flow and promote an existing immutable release to the live prefix

### Workflow Covered By The Script

The script handles the whole fixed flow automatically:

1. **Preflight**
   - check git status and branch state
   - verify Flutter Web project structure
   - detect `fvm` / `flutter` / `dart`
   - ensure `deploy/s3.env` exists
   - verify S3 connectivity

2. **Version**
   - inspect commits since the latest matching tag
   - suggest a SemVer bump
   - optionally accept an explicit or overridden version
   - write the chosen version back to `pubspec.yaml`

3. **Validate**
   - run `flutter pub get`
   - run `build_runner` if needed
   - run `slang` if needed
   - run tests unless `--skip-tests`
   - perform an S3 upload dry-run

4. **Publish**
   - build Flutter Web
   - write `build/web/version.json`
   - upload immutable release assets
   - refresh live assets
   - create and optionally push a git tag

5. **Promote**
   - copy an existing immutable release to the live prefix without rebuilding

## Configuration

Create `deploy/s3.env.example` with non-secret placeholders, then create a local `deploy/s3.env` from it and ensure `deploy/s3.env` is git-ignored.

Example:

```dotenv
S3_ENDPOINT_URL=https://s3.example.com
S3_BUCKET=my-bucket
S3_REGION=auto
S3_LIVE_PREFIX=web
S3_RELEASE_PREFIX=web/releases
BASE_HREF=/
PWA_STRATEGY=none
# AWS_PROFILE=my-profile
```

Required runtime configuration:

- `S3_ENDPOINT_URL`: provider endpoint URL
- `S3_BUCKET`: target bucket
- credentials via `AWS_PROFILE`, CI secrets, or the provider's supported AWS CLI mechanism
- for local uploads, prefer configuring a named AWS CLI profile with `aws configure --profile <new-profile-name>` and setting `AWS_PROFILE=<profile>`

Optional project configuration:

- `S3_REGION`: region passed to AWS CLI; default `auto`
- `S3_LIVE_PREFIX`: live object prefix; default `web`
- `S3_RELEASE_PREFIX`: immutable release prefix; default `web/releases`
- `BASE_HREF`: passed to `flutter build web --base-href`
- `PWA_STRATEGY`: passed to `flutter build web --pwa-strategy`
- `BUILD_WEB_DIR`: override when the web output is not `build/web`
- `BUILD_WASM=1`: add `--wasm`, only after browser/runtime compatibility is verified
- `FLUTTER_CMD`, `DART_CMD`: override command discovery for non-standard projects
- `PRE_BUILD_CMD`, `BUILD_RUNNER_CMD`, `SLANG_CMD`, `TEST_CMD`: override build/test/codegen commands
- `RELEASE_CACHE_CONTROL`, `LIVE_CACHE_CONTROL`, `LIVE_STATIC_CACHE_CONTROL`: customize cache headers for uploaded assets

## Version Helper

If you only need to inspect or write the version without running the full release flow, use `prepare_web_release.py` directly.

It can:

- inspect the current version from `pubspec.yaml`
- find the latest matching git tag
- inspect commits since the last release
- suggest a SemVer bump
- generate a tag name from the selected version
- optionally write the version back to `pubspec.yaml`

## Known Issues

### `S3_RELEASE_PREFIX` as a sub-path of `S3_LIVE_PREFIX`

When `S3_RELEASE_PREFIX` is a child path of `S3_LIVE_PREFIX` (for example `LIVE_PREFIX=web`, `RELEASE_PREFIX=web/releases`), a naive live sync can accidentally delete immutable releases.

**Symptom**: after publishing, older immutable releases under `web/releases/<version>/` are missing their files.

**Fix**: `release_web_s3.py` explicitly excludes `releases/**` during live sync and live refresh operations. The script also warns when it detects nested prefix configuration.

## Resources

### scripts/

- `release_web_s3.py`: main release entry point; handles versioning, validation, upload, publish, and promote
- `prepare_web_release.py`: inspect commits since the latest `web-v*` tag, suggest a SemVer version, generate `web-v<version>`, draft release notes, and optionally update `pubspec.yaml`
- `references/awscli-setup.md`: local setup guide for installing AWS CLI, obtaining `ak/sk`, creating a named profile, and using that profile with `release_web_s3.py`
