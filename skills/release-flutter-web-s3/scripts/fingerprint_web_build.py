#!/usr/bin/env python3
"""Fingerprint cacheable Flutter Web build artifacts and rewrite references."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import struct
import sys
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote


HEX_LEN = 12
HASH_SEGMENT_RE = re.compile(rf"\.[0-9a-f]{{{HEX_LEN}}}(?=\.)")

ASSET_MANIFEST_JSON = "assets/AssetManifest.bin.json"
FONT_MANIFEST_JSON = "assets/FontManifest.json"
INDEX_HTML = "index.html"
BOOTSTRAP_JS = "flutter_bootstrap.js"
APP_MANIFEST = "manifest.json"

UNHASHED_REL_PATHS = {
    ".last_build_id",
    "flutter.js",
    "flutter_service_worker.js",
    "assets/AssetManifest.bin",
    "assets/NOTICES",
}


class CodecError(RuntimeError):
    pass


class ReadBuffer:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    @property
    def has_remaining(self) -> bool:
        return self.pos < len(self.data)

    def align_to(self, alignment: int) -> None:
        mod = self.pos % alignment
        if mod:
            self.pos += alignment - mod

    def get_uint8(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def get_uint16(self) -> int:
        value = int.from_bytes(self.data[self.pos : self.pos + 2], sys.byteorder)
        self.pos += 2
        return value

    def get_uint32(self) -> int:
        value = int.from_bytes(self.data[self.pos : self.pos + 4], sys.byteorder)
        self.pos += 4
        return value

    def get_int32(self) -> int:
        value = int.from_bytes(self.data[self.pos : self.pos + 4], sys.byteorder, signed=True)
        self.pos += 4
        return value

    def get_int64(self) -> int:
        value = int.from_bytes(self.data[self.pos : self.pos + 8], sys.byteorder, signed=True)
        self.pos += 8
        return value

    def get_float64(self) -> float:
        self.align_to(8)
        value = struct.unpack(
            "<d" if sys.byteorder == "little" else ">d",
            self.data[self.pos : self.pos + 8],
        )[0]
        self.pos += 8
        return value

    def get_bytes(self, length: int) -> bytes:
        value = self.data[self.pos : self.pos + length]
        self.pos += length
        return value


class WriteBuffer:
    def __init__(self) -> None:
        self.buf = BytesIO()

    def tell(self) -> int:
        return self.buf.tell()

    def align_to(self, alignment: int) -> None:
        mod = self.tell() % alignment
        if mod:
            self.buf.write(b"\x00" * (alignment - mod))

    def put_uint8(self, value: int) -> None:
        self.buf.write(bytes([value]))

    def put_uint16(self, value: int) -> None:
        self.buf.write(value.to_bytes(2, sys.byteorder))

    def put_uint32(self, value: int) -> None:
        self.buf.write(value.to_bytes(4, sys.byteorder))

    def put_int32(self, value: int) -> None:
        self.buf.write(value.to_bytes(4, sys.byteorder, signed=True))

    def put_int64(self, value: int) -> None:
        self.buf.write(value.to_bytes(8, sys.byteorder, signed=True))

    def put_float64(self, value: float) -> None:
        self.align_to(8)
        self.buf.write(struct.pack("<d" if sys.byteorder == "little" else ">d", value))

    def put_bytes(self, value: bytes) -> None:
        self.buf.write(value)

    def done(self) -> bytes:
        return self.buf.getvalue()


class StandardMessageCodec:
    VALUE_NULL = 0
    VALUE_TRUE = 1
    VALUE_FALSE = 2
    VALUE_INT32 = 3
    VALUE_INT64 = 4
    VALUE_LARGE_INT = 5
    VALUE_FLOAT64 = 6
    VALUE_STRING = 7
    VALUE_UINT8_LIST = 8
    VALUE_INT32_LIST = 9
    VALUE_INT64_LIST = 10
    VALUE_FLOAT64_LIST = 11
    VALUE_LIST = 12
    VALUE_MAP = 13
    VALUE_FLOAT32_LIST = 14

    def read_size(self, buffer: ReadBuffer) -> int:
        value = buffer.get_uint8()
        if value == 254:
            return buffer.get_uint16()
        if value == 255:
            return buffer.get_uint32()
        return value

    def write_size(self, buffer: WriteBuffer, value: int) -> None:
        if value < 254:
            buffer.put_uint8(value)
        elif value <= 0xFFFF:
            buffer.put_uint8(254)
            buffer.put_uint16(value)
        else:
            buffer.put_uint8(255)
            buffer.put_uint32(value)

    def decode_message(self, payload: bytes) -> Any:
        buffer = ReadBuffer(payload)
        result = self.read_value(buffer)
        if buffer.has_remaining:
            raise CodecError("Message corrupted")
        return result

    def encode_message(self, value: Any) -> bytes:
        buffer = WriteBuffer()
        self.write_value(buffer, value)
        return buffer.done()

    def read_value(self, buffer: ReadBuffer) -> Any:
        if not buffer.has_remaining:
            raise CodecError("Message corrupted")
        return self.read_value_of_type(buffer.get_uint8(), buffer)

    def read_value_of_type(self, type_: int, buffer: ReadBuffer) -> Any:
        if type_ == self.VALUE_NULL:
            return None
        if type_ == self.VALUE_TRUE:
            return True
        if type_ == self.VALUE_FALSE:
            return False
        if type_ == self.VALUE_INT32:
            return buffer.get_int32()
        if type_ == self.VALUE_INT64:
            return buffer.get_int64()
        if type_ == self.VALUE_FLOAT64:
            return buffer.get_float64()
        if type_ in {self.VALUE_LARGE_INT, self.VALUE_STRING}:
            length = self.read_size(buffer)
            return buffer.get_bytes(length).decode("utf-8")
        if type_ == self.VALUE_LIST:
            length = self.read_size(buffer)
            return [self.read_value(buffer) for _ in range(length)]
        if type_ == self.VALUE_MAP:
            length = self.read_size(buffer)
            result: dict[Any, Any] = {}
            for _ in range(length):
                key = self.read_value(buffer)
                value = self.read_value(buffer)
                result[key] = value
            return result
        raise CodecError(f"Unsupported value type: {type_}")

    def write_value(self, buffer: WriteBuffer, value: Any) -> None:
        if value is None:
            buffer.put_uint8(self.VALUE_NULL)
        elif value is True:
            buffer.put_uint8(self.VALUE_TRUE)
        elif value is False:
            buffer.put_uint8(self.VALUE_FALSE)
        elif isinstance(value, float):
            buffer.put_uint8(self.VALUE_FLOAT64)
            buffer.put_float64(value)
        elif isinstance(value, int):
            if -0x80000000 <= value <= 0x7FFFFFFF:
                buffer.put_uint8(self.VALUE_INT32)
                buffer.put_int32(value)
            else:
                buffer.put_uint8(self.VALUE_INT64)
                buffer.put_int64(value)
        elif isinstance(value, str):
            encoded = value.encode("utf-8")
            buffer.put_uint8(self.VALUE_STRING)
            self.write_size(buffer, len(encoded))
            buffer.put_bytes(encoded)
        elif isinstance(value, list):
            buffer.put_uint8(self.VALUE_LIST)
            self.write_size(buffer, len(value))
            for item in value:
                self.write_value(buffer, item)
        elif isinstance(value, dict):
            buffer.put_uint8(self.VALUE_MAP)
            self.write_size(buffer, len(value))
            for key, item in value.items():
                self.write_value(buffer, key)
                self.write_value(buffer, item)
        else:
            raise CodecError(f"Unsupported value for encoding: {type(value)!r}")


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        with child.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def insert_hash_in_name(path_str: str, digest: str) -> str:
    path = PurePosixPath(path_str)
    suffix = path.suffix
    if suffix:
        stem = path.name[: -len(suffix)]
        new_name = f"{stem}.{digest}{suffix}"
    else:
        new_name = f"{path.name}.{digest}"
    return str(path.with_name(new_name))


def asset_output_relpath(logical_path: str) -> str:
    return "assets/" + quote(logical_path, safe="/.-_~")


def replace_tokens(text: str, replacements: dict[str, str]) -> str:
    updated = text
    for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        updated = updated.replace(old, new)
    return updated


def cleanup_previous_fingerprint_outputs(build_dir: Path) -> None:
    # Flutter rebuilds `build/web`, but it does not remove unknown hashed files
    # left from a previous fingerprint pass. Remove only the generated hashed
    # artifacts when raw build entrypoints still exist.
    if not (build_dir / "main.dart.js").exists():
        return

    canvaskit_parent = build_dir
    for path in sorted(canvaskit_parent.glob("canvaskit.*")):
        if path.is_dir() and re.fullmatch(rf"canvaskit\.[0-9a-f]{{{HEX_LEN}}}", path.name):
            shutil.rmtree(path)

    for root in [build_dir, build_dir / "icons", build_dir / "assets"]:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            rel = path.relative_to(build_dir).as_posix()
            if rel in UNHASHED_REL_PATHS:
                continue
            if HASH_SEGMENT_RE.search(path.name):
                path.unlink()


def decode_asset_manifest_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = base64.b64decode(payload)
    codec = StandardMessageCodec()
    data = codec.decode_message(raw)
    if not isinstance(data, dict):
        raise CodecError("Unexpected asset manifest payload")
    typed: dict[str, list[dict[str, Any]]] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, list):
            raise CodecError("Unexpected asset manifest structure")
        typed[key] = []
        for item in value:
            if not isinstance(item, dict):
                raise CodecError("Unexpected asset manifest variant structure")
            typed[key].append(dict(item))
    return typed


def load_asset_manifest(build_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return decode_asset_manifest_file(build_dir / ASSET_MANIFEST_JSON)


def write_asset_manifest(build_dir: Path, data: dict[str, list[dict[str, Any]]]) -> None:
    codec = StandardMessageCodec()
    raw = codec.encode_message(data)
    payload = json.dumps(base64.b64encode(raw).decode("ascii"), ensure_ascii=False)
    (build_dir / ASSET_MANIFEST_JSON).write_text(payload, encoding="utf-8")


def load_font_manifest(build_dir: Path) -> list[dict[str, Any]]:
    payload = json.loads((build_dir / FONT_MANIFEST_JSON).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise CodecError("Unexpected font manifest payload")
    return payload


def hash_candidate_files(build_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    physical_mapping: dict[str, str] = {}
    logical_mapping: dict[str, str] = {}

    explicit_files = [
        APP_MANIFEST,
        BOOTSTRAP_JS,
        "favicon.png",
        "main.dart.js",
        "main.dart.mjs",
        "main.dart.wasm",
        "version.json",
        ASSET_MANIFEST_JSON,
        FONT_MANIFEST_JSON,
    ]

    for rel in explicit_files:
        path = build_dir / rel
        if path.exists():
            digest = sha256_hex(path)[:HEX_LEN]
            physical_mapping[rel] = insert_hash_in_name(rel, digest)

    for path in sorted((build_dir / "icons").glob("*")):
        if path.is_file():
            rel = path.relative_to(build_dir).as_posix()
            digest = sha256_hex(path)[:HEX_LEN]
            physical_mapping[rel] = insert_hash_in_name(rel, digest)

    assets_root = build_dir / "assets"
    for path in sorted(assets_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(build_dir).as_posix()
        if rel in {ASSET_MANIFEST_JSON, FONT_MANIFEST_JSON, "assets/AssetManifest.bin", "assets/NOTICES"}:
            continue
        digest = sha256_hex(path)[:HEX_LEN]
        physical_mapping[rel] = insert_hash_in_name(rel, digest)

    canvaskit_dir = build_dir / "canvaskit"
    if canvaskit_dir.exists():
        digest = dir_sha256_hex(canvaskit_dir)[:HEX_LEN]
        physical_mapping["canvaskit"] = f"canvaskit.{digest}"

    asset_manifest_data = load_asset_manifest(build_dir)
    for variants in asset_manifest_data.values():
        for item in variants:
            asset = item.get("asset")
            if isinstance(asset, str):
                physical_old = asset_output_relpath(asset)
                physical_new = physical_mapping.get(physical_old)
                if physical_new:
                    logical_mapping[asset] = insert_hash_in_name(asset, Path(physical_new).stem.split(".")[-1])

    font_manifest_data = load_font_manifest(build_dir)
    for family in font_manifest_data:
        fonts = family.get("fonts")
        if not isinstance(fonts, list):
            continue
        for font in fonts:
            if not isinstance(font, dict):
                continue
            asset = font.get("asset")
            if isinstance(asset, str):
                physical_old = asset_output_relpath(asset)
                physical_new = physical_mapping.get(physical_old)
                if physical_new:
                    logical_mapping[asset] = insert_hash_in_name(asset, Path(physical_new).stem.split(".")[-1])

    return physical_mapping, logical_mapping


def rename_paths(build_dir: Path, mapping: dict[str, str]) -> None:
    directory_moves = [(old, new) for old, new in mapping.items() if Path(old).suffix == "" and old != new]
    file_moves = [(old, new) for old, new in mapping.items() if Path(old).suffix != "" and old != new]

    for old, new in directory_moves:
        src = build_dir / old
        dst = build_dir / new
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

    for old, new in file_moves:
        src = build_dir / old
        dst = build_dir / new
        if dst.exists():
            dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)


def rewrite_asset_manifest(
    build_dir: Path,
    logical_mapping: dict[str, str],
    relpath: str,
) -> None:
    payload = load_asset_manifest(build_dir)
    for variants in payload.values():
        for item in variants:
            asset = item.get("asset")
            if isinstance(asset, str) and asset in logical_mapping:
                item["asset"] = logical_mapping[asset]
    write_asset_manifest(build_dir, payload)
    if relpath != ASSET_MANIFEST_JSON:
        rename_paths(build_dir, {ASSET_MANIFEST_JSON: relpath})


def rewrite_font_manifest(
    build_dir: Path,
    logical_mapping: dict[str, str],
    relpath: str,
) -> None:
    payload = load_font_manifest(build_dir)
    for family in payload:
        fonts = family.get("fonts")
        if not isinstance(fonts, list):
            continue
        for font in fonts:
            if not isinstance(font, dict):
                continue
            asset = font.get("asset")
            if isinstance(asset, str) and asset in logical_mapping:
                font["asset"] = logical_mapping[asset]
    (build_dir / FONT_MANIFEST_JSON).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    if relpath != FONT_MANIFEST_JSON:
        rename_paths(build_dir, {FONT_MANIFEST_JSON: relpath})


def rewrite_text_file(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    updated = replace_tokens(text, replacements)
    path.write_text(updated, encoding="utf-8")


def fingerprint_build(build_dir: Path) -> dict[str, Any]:
    if not build_dir.exists():
        raise SystemExit(f"Build directory not found: {build_dir}")

    cleanup_previous_fingerprint_outputs(build_dir)
    physical_mapping, logical_mapping = hash_candidate_files(build_dir)
    hashed_files: set[str] = set()

    canvaskit_new = physical_mapping.pop("canvaskit", None)
    if canvaskit_new:
        rename_paths(build_dir, {"canvaskit": canvaskit_new})
        for path in sorted((build_dir / canvaskit_new).rglob("*")):
            if path.is_file():
                hashed_files.add(path.relative_to(build_dir).as_posix())

    asset_manifest_new = physical_mapping.pop(ASSET_MANIFEST_JSON, ASSET_MANIFEST_JSON)
    font_manifest_new = physical_mapping.pop(FONT_MANIFEST_JSON, FONT_MANIFEST_JSON)

    rename_paths(build_dir, physical_mapping)
    hashed_files.update(physical_mapping.values())

    rewrite_asset_manifest(build_dir, logical_mapping, asset_manifest_new)
    hashed_files.add(asset_manifest_new)

    rewrite_font_manifest(build_dir, logical_mapping, font_manifest_new)
    hashed_files.add(font_manifest_new)

    manifest_rel = physical_mapping.get(APP_MANIFEST, APP_MANIFEST)
    bootstrap_rel = physical_mapping.get(BOOTSTRAP_JS, BOOTSTRAP_JS)
    main_js_rel = physical_mapping.get("main.dart.js", "main.dart.js")
    main_mjs_rel = physical_mapping.get("main.dart.mjs", "main.dart.mjs")
    main_wasm_rel = physical_mapping.get("main.dart.wasm", "main.dart.wasm")
    version_rel = physical_mapping.get("version.json", "version.json")
    favicon_rel = physical_mapping.get("favicon.png", "favicon.png")
    icon_192_rel = physical_mapping.get("icons/Icon-192.png", "icons/Icon-192.png")

    root_replacements = {
        APP_MANIFEST: manifest_rel,
        BOOTSTRAP_JS: bootstrap_rel,
        "favicon.png": favicon_rel,
        "icons/Icon-192.png": icon_192_rel,
        "assets/fonts/MaterialIcons-Regular.otf": physical_mapping.get(
            "assets/fonts/MaterialIcons-Regular.otf",
            "assets/fonts/MaterialIcons-Regular.otf",
        ),
    }
    rewrite_text_file(build_dir / INDEX_HTML, root_replacements)

    manifest_path = build_dir / manifest_rel
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for icon in manifest_payload.get("icons", []):
        src = icon.get("src")
        if isinstance(src, str):
            icon["src"] = physical_mapping.get(f"icons/{Path(src).name}", src)
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    bootstrap_path = build_dir / bootstrap_rel
    rewrite_text_file(
        bootstrap_path,
        {
            '"mainWasmPath":"main.dart.wasm"': f'"mainWasmPath":"{main_wasm_rel}"',
            '"jsSupportRuntimePath":"main.dart.mjs"': f'"jsSupportRuntimePath":"{main_mjs_rel}"',
            '"mainJsPath":"main.dart.js"': f'"mainJsPath":"{main_js_rel}"',
            '"canvaskit"': f'"{canvaskit_new}"' if canvaskit_new else '"canvaskit"',
        },
    )

    main_js_path = build_dir / main_js_rel
    rewrite_text_file(
        main_js_path,
        {
            "AssetManifest.bin.json": Path(asset_manifest_new).name,
            "FontManifest.json": Path(font_manifest_new).name,
            "version.json": version_rel,
            '"canvaskit"': f'"{canvaskit_new}"' if canvaskit_new else '"canvaskit"',
        },
    )

    stable_files = {
        path.relative_to(build_dir).as_posix()
        for path in build_dir.rglob("*")
        if path.is_file() and path.relative_to(build_dir).as_posix() not in hashed_files
    }

    return {
        "build_dir": str(build_dir),
        "hashed_files": sorted(hashed_files),
        "stable_files": sorted(stable_files),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fingerprint cacheable Flutter Web build artifacts.")
    parser.add_argument("build_dir", help="Path to build/web")
    parser.add_argument(
        "--manifest-out",
        help="Optional JSON output path for the generated fingerprint manifest",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = fingerprint_build(Path(args.build_dir).resolve())
    if args.manifest_out:
        Path(args.manifest_out).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
