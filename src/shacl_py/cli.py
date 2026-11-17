"""Command line entry points."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import yaml

from shacl_py.records import load_records


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shacl-py")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create paper metadata without overwriting")
    init.add_argument("path", type=Path)
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
            target = args.path / "metadata.yaml"
            data = {
                "pid": f"urn:uuid:{uuid4()}",
                "display_label": args.path.resolve().name,
                "description": "Replace with the paper description.",
                "source_url": "https://example.org/replace-with-paper-url",
                "review_status": "unreviewed",
                "local_folder": ".",
            }
            with target.open("x") as stream:
                yaml.safe_dump(data, stream, sort_keys=False)
            print(
                f"Created {target}; replace the placeholder description and source URL."
            )
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
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
