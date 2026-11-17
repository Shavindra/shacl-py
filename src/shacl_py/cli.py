"""Command line entry points."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import yaml

from shacl_py.records import load_records


def generate_record(folder):
    title = (
        folder.resolve().name.replace("_", " ").replace("-", " ").strip() or folder.name
    )
    data = {
        "pid": f"urn:uuid:{uuid4()}",
        "display_label": title,
        "review_status": "unreviewed",
        "local_folder": ".",
    }
    readme = folder / "README.md"
    if readme.is_file() and not readme.is_symlink():
        with readme.open("rb") as stream:
            lines = stream.read(65536).decode("utf-8", errors="replace").splitlines()
        for line in lines:
            if line.startswith("# ") and line[2:].strip():
                data["display_label"] = line[2:].strip()
                break
        for line in lines:
            if (
                line.strip()
                and line[0].isalnum()
                and not line.startswith(("http", "DOI:"))
            ):
                data["description"] = line.strip()
                break
        for line in lines:
            source = re.fullmatch(
                r"(?:DOI|Source):\s*(https?://\S+|10\.\d{4,9}/\S+)",
                line.strip(),
                re.IGNORECASE,
            )
            if source:
                url = source.group(1)
                data["source_url"] = (
                    "https://doi.org/" + url if url.startswith("10.") else url
                )
                break
    # These files describe this paper, rather than the enclosing dataset.
    for name in ("metalad.json", "paper.json"):
        path = folder / name
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > 1_000_000:
            raise ValueError(f"{path}: exceeds 1 MB")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        if name == "metalad.json" and isinstance(record, dict):
            record = record.get("extracted_metadata")
        if not isinstance(record, dict):
            raise TypeError(f"{path}: expected a single paper metadata object")
        keys = {
            "display_label": ("display_label", "title"),
            "description": ("description",),
            "source_url": ("source_url", "url", "doi"),
        }
        if name == "paper.json":
            keys["pid"] = ("pid",)
        for field, aliases in keys.items():
            for key in aliases:
                value = record.get(key)
                if not isinstance(value, str) or not value.strip():
                    continue
                value = value.strip()
                if field == "source_url":
                    if re.fullmatch(r"10\.\d{4,9}/\S+", value):
                        value = "https://doi.org/" + value
                    if not re.match(r"https?://[^\s/]+", value):
                        continue
                if field == "pid" and not re.fullmatch(r"\S+:\S+", value):
                    continue
                data[field] = value
                break
    target = folder / "metadata.yaml"
    with target.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)
    print(f"Created {target}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shacl-py")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create paper metadata without overwriting")
    init.add_argument("path", type=Path)
    generate = commands.add_parser(
        "generate", help="Generate missing records for immediate paper folders"
    )
    generate.add_argument(
        "path", type=Path, help="Folder containing one directory per paper"
    )
    validate = commands.add_parser(
        "validate", help="Validate all metadata beneath a root"
    )
    validate.add_argument("path", type=Path)
    serve = commands.add_parser("serve", help="Start the read-only local viewer")
    serve.add_argument("path", type=Path)
    serve.add_argument("--port", type=int, default=8501)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            args.path.mkdir(parents=True, exist_ok=True)
            generate_record(args.path)
            return 0
        if args.command == "generate":
            for folder in sorted(args.path.iterdir()):
                if (
                    folder.name.startswith(".")
                    or folder.is_symlink()
                    or not folder.is_dir()
                ):
                    continue
                try:
                    if os.path.lexists(folder / "metadata.yaml"):
                        print(f"Kept {folder / 'metadata.yaml'}")
                        continue
                    generate_record(folder)
                except FileExistsError:
                    print(f"Kept {folder / 'metadata.yaml'}")
            return 0
        root = args.path.resolve()
        records, errors = load_records(root)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        if args.command == "validate":
            print(f"Validated {len(records)} paper record(s).")
            return 0
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        env = os.environ.copy()
        env["SHACL_PY_ROOT"] = str(root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(__file__).with_name("app.py")),
                "--server.address=127.0.0.1",
                f"--server.port={args.port}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
                "--server.fileWatcherType=none",
                "--theme.base=light",
                "--theme.primaryColor=#000000",
                "--theme.backgroundColor=#FFFFFF",
                "--theme.secondaryBackgroundColor=#F0F0F0",
                "--theme.textColor=#000000",
            ],
            env=env,
            cwd=Path(__file__).parent,
        )
    except (OSError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
