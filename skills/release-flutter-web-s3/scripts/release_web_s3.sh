#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${PROJECT_ROOT:-}" ]]; then
  ROOT_DIR="$(cd "$PROJECT_ROOT" && pwd)"
elif [[ -f "$SCRIPT_DIR/../pubspec.yaml" ]]; then
  ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [[ -f pubspec.yaml ]]; then
  ROOT_DIR="$(pwd)"
elif command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  ROOT_DIR="$(git rev-parse --show-toplevel)"
else
  printf '[release-web-s3] ERROR: Unable to find Flutter project root. Run from the app root or set PROJECT_ROOT.\n' >&2
  exit 1
fi

cd "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Build Flutter Web and publish it to an S3-compatible bucket.

Usage:
  scripts/release_web_s3.sh [--dry-run] [--skip-tests] [--skip-build]
  scripts/release_web_s3.sh --promote-only <release-id> [--dry-run]

Configuration is read from environment variables and, by default, deploy/s3.env.
Copy deploy/s3.env.example to deploy/s3.env for local use.

Required:
  S3_ENDPOINT_URL          S3-compatible endpoint, for example https://s3.example.com
  S3_BUCKET                Bucket name

Common:
  S3_REGION                Region passed to AWS CLI. Default: auto
  S3_LIVE_PREFIX           Live object prefix. Default: web
  S3_RELEASE_PREFIX        Immutable release prefix. Default: web/releases
  BASE_HREF                Flutter Web base href. Default: /
  PWA_STRATEGY             Flutter Web PWA strategy. Default: none
  BUILD_WASM=1             Add --wasm for skwasm-capable builds. Default: 0
  RELEASE_ID               Release directory name. Default: pubspec.yaml version
  AWS_PROFILE              Optional AWS CLI profile for local credentials
  PROJECT_ROOT             Flutter project root if this script is not stored under scripts/
  FLUTTER_CMD              Flutter command. Auto-detects "fvm flutter" when FVM is present
  DART_CMD                 Dart command. Auto-detects "fvm dart" when FVM is present
  PRE_BUILD_CMD            Optional command to run before tests and build
  BUILD_RUNNER_CMD         Optional build_runner command
  SLANG_CMD                Optional Slang generation command. Default: auto when slang is configured
  TEST_CMD                 Test command. Default: "<flutter> test"

Compatibility switches, only enable when the provider requires them:
  S3_ADDRESSING_STYLE      path, virtual, or auto
  AWS_REQUEST_CHECKSUM_CALCULATION=when_required
  AWS_RESPONSE_CHECKSUM_VALIDATION=when_required

Safety:
  ALLOW_DIRTY=1            Allow publishing from a dirty git worktree
USAGE
}

log() {
  printf '[release-web-s3] %s\n' "$*"
}

fail() {
  printf '[release-web-s3] ERROR: %s\n' "$*" >&2
  exit 1
}

bool_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_env() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "Missing required environment variable: $name"
}

project_uses_fvm() {
  [[ -f .fvm/fvm_config.json || -f .fvmrc || -d .fvm ]]
}

detect_flutter_commands() {
  if [[ -n "${FLUTTER_CMD:-}" ]]; then
    read -r -a FLUTTER_BIN <<< "$FLUTTER_CMD"
  elif project_uses_fvm; then
    FLUTTER_BIN=(fvm flutter)
  else
    FLUTTER_BIN=(flutter)
  fi

  if [[ -n "${DART_CMD:-}" ]]; then
    read -r -a DART_BIN <<< "$DART_CMD"
  elif project_uses_fvm; then
    DART_BIN=(fvm dart)
  else
    DART_BIN=(dart)
  fi

  [[ "${#FLUTTER_BIN[@]}" -gt 0 ]] || fail "FLUTTER_CMD cannot be empty"
  [[ "${#DART_BIN[@]}" -gt 0 ]] || fail "DART_CMD cannot be empty"
  require_cmd "${FLUTTER_BIN[0]}"
  require_cmd "${DART_BIN[0]}"
}

quote_cmd() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
}

run_cmd() {
  quote_cmd "$@"
  "$@"
}

run_shell_cmd() {
  printf '+ %s\n' "$*"
  bash -lc "$*"
}

strip_edge_slashes() {
  local value="${1:-}"
  value="${value#/}"
  value="${value%/}"
  printf '%s' "$value"
}

env_or_default() {
  local name="$1"
  local default="$2"
  if [[ "${!name+set}" == "set" ]]; then
    printf '%s' "${!name}"
  else
    printf '%s' "$default"
  fi
}

join_prefix() {
  local left
  local right
  left="$(strip_edge_slashes "${1:-}")"
  right="$(strip_edge_slashes "${2:-}")"
  if [[ -z "$left" ]]; then
    printf '%s' "$right"
  elif [[ -z "$right" ]]; then
    printf '%s' "$left"
  else
    printf '%s/%s' "$left" "$right"
  fi
}

s3_uri() {
  local prefix
  prefix="$(strip_edge_slashes "${1:-}")"
  if [[ -z "$prefix" ]]; then
    printf 's3://%s' "$S3_BUCKET"
  else
    printf 's3://%s/%s' "$S3_BUCKET" "$prefix"
  fi
}

read_pubspec_value() {
  local key="$1"
  sed -nE "s/^${key}:[[:space:]]*['\"]?([^'\"#[:space:]]+)['\"]?.*/\1/p" pubspec.yaml | head -n 1
}

json_escape() {
  local value="${1:-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

json_field() {
  local key="$1"
  local value="$2"
  local suffix="${3-,}"
  printf '  "%s": "%s"%s\n' "$key" "$(json_escape "$value")" "$suffix"
}

DRY_RUN="${DRY_RUN:-0}"
SKIP_TESTS="${SKIP_TESTS:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
PROMOTE_ONLY_RELEASE_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --promote-only)
      [[ $# -ge 2 ]] || fail "--promote-only requires a release id"
      PROMOTE_ONLY_RELEASE_ID="$2"
      SKIP_BUILD=1
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE-deploy/s3.env}"
if [[ -n "$DEPLOY_ENV_FILE" && -f "$DEPLOY_ENV_FILE" ]]; then
  log "Loading environment from $DEPLOY_ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$DEPLOY_ENV_FILE"
  set +a
fi

require_cmd git
require_cmd aws
if ! bool_enabled "$SKIP_BUILD"; then
  detect_flutter_commands
fi

require_env S3_ENDPOINT_URL
require_env S3_BUCKET

S3_REGION="${S3_REGION:-auto}"
S3_LIVE_PREFIX="$(strip_edge_slashes "$(env_or_default S3_LIVE_PREFIX web)")"
S3_RELEASE_PREFIX="$(strip_edge_slashes "$(env_or_default S3_RELEASE_PREFIX web/releases)")"
BASE_HREF="${BASE_HREF:-/}"
BUILD_WEB_DIR="${BUILD_WEB_DIR:-build/web}"
PWA_STRATEGY="${PWA_STRATEGY:-none}"
BUILD_WASM="${BUILD_WASM:-0}"
RELEASE_CACHE_CONTROL="${RELEASE_CACHE_CONTROL:-public,max-age=31536000,immutable}"
LIVE_CACHE_CONTROL="${LIVE_CACHE_CONTROL:-no-cache,max-age=0,must-revalidate}"
LIVE_STATIC_CACHE_CONTROL="${LIVE_STATIC_CACHE_CONTROL:-public,max-age=86400}"

if [[ -n "${S3_ADDRESSING_STYLE:-}" ]]; then
  case "$S3_ADDRESSING_STYLE" in
    path|virtual|auto) ;;
    *) fail "S3_ADDRESSING_STYLE must be one of: path, virtual, auto" ;;
  esac

  AWS_CONFIG_FILE_TEMP="$(mktemp)"
  trap 'rm -f "$AWS_CONFIG_FILE_TEMP"' EXIT
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    printf '[profile %s]\ns3 =\n  addressing_style = %s\n' "$AWS_PROFILE" "$S3_ADDRESSING_STYLE" > "$AWS_CONFIG_FILE_TEMP"
  else
    printf '[default]\ns3 =\n  addressing_style = %s\n' "$S3_ADDRESSING_STYLE" > "$AWS_CONFIG_FILE_TEMP"
  fi
  export AWS_CONFIG_FILE="$AWS_CONFIG_FILE_TEMP"
  log "Compatibility enabled: S3_ADDRESSING_STYLE=$S3_ADDRESSING_STYLE"
fi

if [[ -n "${AWS_REQUEST_CHECKSUM_CALCULATION:-}" ]]; then
  log "Compatibility enabled: AWS_REQUEST_CHECKSUM_CALCULATION=$AWS_REQUEST_CHECKSUM_CALCULATION"
fi

if [[ -n "${AWS_RESPONSE_CHECKSUM_VALIDATION:-}" ]]; then
  log "Compatibility enabled: AWS_RESPONSE_CHECKSUM_VALIDATION=$AWS_RESPONSE_CHECKSUM_VALIDATION"
fi

if [[ -z "$PROMOTE_ONLY_RELEASE_ID" ]]; then
  PUBSPEC_NAME="$(read_pubspec_value name)"
  [[ -n "$PUBSPEC_NAME" ]] || fail "Unable to read package name from pubspec.yaml"
  PUBSPEC_VERSION="$(read_pubspec_value version)"
  [[ -n "$PUBSPEC_VERSION" ]] || fail "Unable to read version from pubspec.yaml"
  RELEASE_ID="${RELEASE_ID:-$PUBSPEC_VERSION}"
else
  RELEASE_ID="$PROMOTE_ONLY_RELEASE_ID"
fi

if [[ ! "$RELEASE_ID" =~ ^[A-Za-z0-9._+-]+$ ]]; then
  fail "RELEASE_ID may only contain letters, numbers, dot, underscore, plus, or dash: $RELEASE_ID"
fi

if ! bool_enabled "${ALLOW_DIRTY:-0}"; then
  if [[ -n "$(git status --porcelain)" ]]; then
    git status --short >&2
    fail "Working tree is dirty. Commit/stash changes first, or set ALLOW_DIRTY=1 for an explicit non-reproducible publish."
  fi
else
  log "Safety override enabled: ALLOW_DIRTY=1"
fi

AWS_ARGS=(--endpoint-url "$S3_ENDPOINT_URL" --region "$S3_REGION")
if [[ -n "${AWS_PROFILE:-}" ]]; then
  AWS_ARGS+=(--profile "$AWS_PROFILE")
fi

SYNC_ARGS=(--delete)
if bool_enabled "$DRY_RUN"; then
  SYNC_ARGS+=(--dryrun)
  log "Dry run enabled; no objects will be changed."
fi

LIVE_URI="$(s3_uri "$S3_LIVE_PREFIX")"
RELEASE_URI="$(s3_uri "$(join_prefix "$S3_RELEASE_PREFIX" "$RELEASE_ID")")"
GIT_SHA="$(git rev-parse HEAD)"
BUILD_TIME_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

log "Release id: $RELEASE_ID"
log "Endpoint: $S3_ENDPOINT_URL"
log "Bucket: $S3_BUCKET"
log "Release target: $RELEASE_URI"
log "Live target: $LIVE_URI"
log "Base href: $BASE_HREF"
log "PWA strategy: $PWA_STRATEGY"

if bool_enabled "$BUILD_WASM"; then
  log "Compatibility change enabled: BUILD_WASM=1 adds --wasm. Test browser/plugin compatibility before promoting."
fi

refresh_live_entrypoints() {
  local source="$1"
  local cmd=(
    aws "${AWS_ARGS[@]}" s3 cp "$source" "$LIVE_URI"
    --recursive
  )

  if bool_enabled "$DRY_RUN"; then
    cmd+=(--dryrun)
  fi

  cmd+=(
    --exclude "*"
    --include "index.html"
    --include "*.html"
    --include "flutter.js"
    --include "flutter_bootstrap.js"
    --include "flutter_service_worker.js"
    --include "manifest.json"
    --include "version.json"
    --cache-control "$LIVE_CACHE_CONTROL"
  )

  if [[ "$source" == s3://* ]]; then
    cmd+=(--metadata-directive REPLACE)
  fi

  run_cmd "${cmd[@]}"
}

refresh_live_static_assets() {
  local source="$1"
  local cmd=(
    aws "${AWS_ARGS[@]}" s3 cp "$source" "$LIVE_URI"
    --recursive
  )

  if bool_enabled "$DRY_RUN"; then
    cmd+=(--dryrun)
  fi

  cmd+=(
    --exclude "*"
    --include "assets/fonts/*"
    --include "canvaskit/*"
    --include "icons/*"
    --include "favicon.png"
    --cache-control "$LIVE_STATIC_CACHE_CONTROL"
  )

  if [[ "$source" == s3://* ]]; then
    cmd+=(--metadata-directive REPLACE)
  fi

  run_cmd "${cmd[@]}"
}

if [[ -n "$PROMOTE_ONLY_RELEASE_ID" ]]; then
  log "Promoting an existing release without rebuilding."
  run_cmd aws "${AWS_ARGS[@]}" s3 sync "$RELEASE_URI" "$LIVE_URI" \
    "${SYNC_ARGS[@]}" \
    --cache-control "$LIVE_CACHE_CONTROL" \
    --metadata-directive REPLACE
  refresh_live_static_assets "$RELEASE_URI"
  refresh_live_entrypoints "$RELEASE_URI"
  exit 0
fi

if ! bool_enabled "$SKIP_BUILD"; then
  run_cmd "${FLUTTER_BIN[@]}" pub get
  if [[ -n "${PRE_BUILD_CMD:-}" ]]; then
    run_shell_cmd "$PRE_BUILD_CMD"
  fi
  if [[ -n "${BUILD_RUNNER_CMD:-}" ]]; then
    run_shell_cmd "$BUILD_RUNNER_CMD"
  fi
  if [[ -n "${SLANG_CMD:-}" ]]; then
    run_shell_cmd "$SLANG_CMD"
  elif [[ -f slang.yaml ]] || grep -q '^[[:space:]]*slang:' pubspec.yaml; then
    run_cmd "${DART_BIN[@]}" run slang
  fi
  if ! bool_enabled "$SKIP_TESTS"; then
    if [[ -n "${TEST_CMD:-}" ]]; then
      run_shell_cmd "$TEST_CMD"
    else
      run_cmd "${FLUTTER_BIN[@]}" test
    fi
  else
    log "Skipping tests because SKIP_TESTS=1 or --skip-tests was provided."
  fi
  BUILD_ARGS=(build web --release --base-href "$BASE_HREF" "--pwa-strategy=$PWA_STRATEGY")
  if bool_enabled "$BUILD_WASM"; then
    BUILD_ARGS+=(--wasm)
  fi
  run_cmd "${FLUTTER_BIN[@]}" "${BUILD_ARGS[@]}"
else
  log "Skipping build because SKIP_BUILD=1, --skip-build, or --promote-only was provided."
fi

[[ -d "$BUILD_WEB_DIR" ]] || fail "Build output not found: $BUILD_WEB_DIR"

APP_VERSION="${PUBSPEC_VERSION%%+*}"
APP_BUILD_NUMBER=""
if [[ "$PUBSPEC_VERSION" == *+* ]]; then
  APP_BUILD_NUMBER="${PUBSPEC_VERSION#*+}"
fi

{
  printf '{\n'
  json_field app_name "$PUBSPEC_NAME"
  json_field version "$APP_VERSION"
  json_field package_name "$PUBSPEC_NAME"
  json_field build_number "$APP_BUILD_NUMBER"
  json_field releaseId "$RELEASE_ID"
  json_field gitSha "$GIT_SHA"
  json_field builtAt "$BUILD_TIME_UTC"
  json_field baseHref "$BASE_HREF"
  json_field s3Bucket "$S3_BUCKET"
  json_field s3LivePrefix "$S3_LIVE_PREFIX"
  json_field s3ReleasePrefix "$S3_RELEASE_PREFIX" ""
  printf '}\n'
} > "$BUILD_WEB_DIR/version.json"

run_cmd aws "${AWS_ARGS[@]}" s3 sync "$BUILD_WEB_DIR" "$RELEASE_URI" \
  "${SYNC_ARGS[@]}" \
  --cache-control "$RELEASE_CACHE_CONTROL"

run_cmd aws "${AWS_ARGS[@]}" s3 sync "$BUILD_WEB_DIR" "$LIVE_URI" \
  "${SYNC_ARGS[@]}" \
  --cache-control "$LIVE_CACHE_CONTROL"

refresh_live_static_assets "$BUILD_WEB_DIR"
refresh_live_entrypoints "$BUILD_WEB_DIR"

log "Publish finished."
