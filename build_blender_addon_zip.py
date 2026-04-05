#!/usr/bin/env python3
"""Build a Blender-installable add-on ZIP from source files."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

ADDON_DIR_NAME = "io_scene_flightgear_btg"
ENTRYPOINT_NAME = "io_scene_flightgear_btg.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Blender-installable ZIP from src/*.py"
    )
    parser.add_argument(
        "--source-dir",
        default="src",
        help="Directory containing addon source .py files (default: src)",
    )
    parser.add_argument(
        "--output-dir",
        default="releases",
        help="Directory for generated ZIP artifacts (default: releases)",
    )
    parser.add_argument(
        "--zip-name",
        default="",
        help="Optional explicit ZIP file name (default: blender-btg-import-export-<version>.zip)",
    )
    return parser.parse_args()


def _extract_version(entrypoint: Path) -> str:
    text = entrypoint.read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)', text)
    if not match:
        raise RuntimeError(f"Could not find bl_info version tuple in {entrypoint}")
    return ".".join(match.groups())


def _collect_source_files(source_dir: Path) -> list[Path]:
    files = sorted(source_dir.glob("*.py"))
    if not files:
        raise RuntimeError(f"No Python files found in {source_dir}")
    entrypoint = source_dir / ENTRYPOINT_NAME
    if not entrypoint.exists():
        raise RuntimeError(f"Missing expected entrypoint: {entrypoint}")
    return files


def _write_addon_zip(source_files: list[Path], zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source_file in source_files:
            if source_file.name == ENTRYPOINT_NAME:
                arcname = f"{ADDON_DIR_NAME}/__init__.py"
            else:
                arcname = f"{ADDON_DIR_NAME}/{source_file.name}"
            zf.write(source_file, arcname)


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parent
    source_dir = (repo_root / args.source_dir).resolve()
    output_dir = (repo_root / args.output_dir).resolve()

    source_files = _collect_source_files(source_dir)
    version = _extract_version(source_dir / ENTRYPOINT_NAME)

    if args.zip_name:
        zip_name = args.zip_name
    else:
        zip_name = f"blender-btg-import-export-{version}.zip"

    zip_path = output_dir / zip_name
    _write_addon_zip(source_files, zip_path)

    size_bytes = zip_path.stat().st_size
    print(f"Built {zip_path} ({size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
