#!/usr/bin/env python3
"""Verify that a fingerprinted Flutter Web build is internally consistent."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def fail(message: str) -> None:
    raise SystemExit(f"[verify-fingerprint] ERROR: {message}")


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        fail(f"Unable to import helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_contains(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    require(needle in text, f"{path.name} does not reference {needle}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a fingerprinted Flutter Web build.")
    parser.add_argument("build_dir", help="Path to build/web")
    parser.add_argument(
        "--manifest",
        help="Path to web_fingerprint_manifest.json. Defaults to <build_dir>/../web_fingerprint_manifest.json",
    )
    parser.add_argument(
        "--fingerprint-script",
        help="Path to fingerprint_web_build.py. Defaults to sibling of this script.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    build_dir = Path(args.build_dir).resolve()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else (build_dir.parent / "web_fingerprint_manifest.json").resolve()
    )
    script_path = (
        Path(args.fingerprint_script).resolve()
        if args.fingerprint_script
        else (Path(__file__).resolve().parent / "fingerprint_web_build.py")
    )

    require(build_dir.exists(), f"Build directory not found: {build_dir}")
    require(manifest_path.exists(), f"Fingerprint manifest not found: {manifest_path}")
    require(script_path.exists(), f"Fingerprint script not found: {script_path}")

    module = load_module(script_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashed_files = manifest.get("hashed_files", [])
    stable_files = manifest.get("stable_files", [])

    require(isinstance(hashed_files, list) and hashed_files, "hashed_files is missing or empty")
    require(isinstance(stable_files, list) and stable_files, "stable_files is missing or empty")

    for rel in hashed_files + stable_files:
        require((build_dir / rel).exists(), f"Missing file declared in manifest: {rel}")

    require("index.html" in stable_files, "index.html must remain stable")
    require("flutter.js" in stable_files, "flutter.js must remain stable")

    hashed_lookup = set(hashed_files)

    def pick(prefix: str, suffix: str = "") -> str:
        matches = [rel for rel in hashed_lookup if rel.startswith(prefix) and rel.endswith(suffix)]
        require(len(matches) == 1, f"Expected exactly one hashed match for {prefix}*{suffix}, got {matches}")
        return matches[0]

    bootstrap_rel = pick("flutter_bootstrap.", ".js")
    manifest_rel = pick("manifest.", ".json")
    favicon_rel = pick("favicon.", ".png")
    main_js_rel = pick("main.dart.", ".js")
    main_mjs_rel = pick("main.dart.", ".mjs")
    main_wasm_rel = pick("main.dart.", ".wasm")
    version_rel = pick("version.", ".json")
    asset_manifest_rel = pick("assets/AssetManifest.bin.", ".json")
    font_manifest_rel = pick("assets/FontManifest.", ".json")

    canvaskit_dirs = sorted({rel.split("/", 1)[0] for rel in hashed_files if rel.startswith("canvaskit.")})
    require(len(canvaskit_dirs) == 1, f"Expected exactly one hashed canvaskit directory, got {canvaskit_dirs}")
    canvaskit_dir = canvaskit_dirs[0]

    index_html = build_dir / "index.html"
    require_contains(index_html, bootstrap_rel)
    require_contains(index_html, manifest_rel)
    require_contains(index_html, favicon_rel)

    bootstrap_js = build_dir / bootstrap_rel
    require_contains(bootstrap_js, main_js_rel)
    require_contains(bootstrap_js, main_mjs_rel)
    require_contains(bootstrap_js, main_wasm_rel)
    require_contains(bootstrap_js, canvaskit_dir)

    main_js = build_dir / main_js_rel
    require_contains(main_js, Path(asset_manifest_rel).name)
    require_contains(main_js, Path(font_manifest_rel).name)
    require_contains(main_js, version_rel)
    require_contains(main_js, canvaskit_dir)

    app_manifest = json.loads((build_dir / manifest_rel).read_text(encoding="utf-8"))
    icon_sources = [icon.get("src") for icon in app_manifest.get("icons", []) if isinstance(icon, dict)]
    require(icon_sources, f"{manifest_rel} does not contain icons")
    for src in icon_sources:
        require(isinstance(src, str) and src in hashed_lookup, f"{manifest_rel} references non-hashed icon: {src}")

    font_manifest = json.loads((build_dir / font_manifest_rel).read_text(encoding="utf-8"))
    for family in font_manifest:
        for font in family.get("fonts", []):
            asset = font.get("asset")
            require(isinstance(asset, str), "Font manifest contains a non-string asset")
            physical = module.asset_output_relpath(asset)
            require(physical in hashed_lookup, f"Font manifest asset is not fingerprinted: {asset}")

    asset_manifest_payload = module.decode_asset_manifest_file(build_dir / asset_manifest_rel)
    require(asset_manifest_payload, "Asset manifest payload is empty")
    checked_assets = 0
    for variants in asset_manifest_payload.values():
        for item in variants:
            asset = item.get("asset")
            require(isinstance(asset, str), "Asset manifest contains a non-string asset entry")
            physical = module.asset_output_relpath(asset)
            require(physical in hashed_lookup, f"Asset manifest asset is not fingerprinted: {asset}")
            checked_assets += 1
    require(checked_assets > 0, "Asset manifest does not contain any asset variants")

    print(
        json.dumps(
            {
                "build_dir": str(build_dir),
                "manifest": str(manifest_path),
                "checked_hashed_files": len(hashed_files),
                "checked_stable_files": len(stable_files),
                "canvaskit_dir": canvaskit_dir,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
