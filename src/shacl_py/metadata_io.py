"""Round-trip YAML and publish validated setup files together."""

import hashlib
import os
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import yaml
from filelock import FileLock
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError as RoundTripError

from shacl_py.files import read_metadata


@dataclass
class MetadataFile:
    path: Path
    original: str | None
    data: dict

    @classmethod
    def read(cls, path):
        if not os.path.lexists(path):
            return cls(path, None, {})
        try:
            text = read_metadata(path)
            editor = YAML(typ="rt")
            editor.preserve_quotes = True
            # The same safe YAML representation must be readable by the viewer.
            data = editor.load(text)
            if not isinstance(data, dict) or yaml.safe_load(text) != data:
                raise ValueError("expected an unambiguous YAML mapping")
            return cls(path, text, data)
        except (
            OSError,
            TypeError,
            ValueError,
            yaml.YAMLError,
            RoundTripError,
        ) as error:
            raise ValueError(f"{path}: {error}") from error

    def serialise(self):
        if self.original is not None and self.data == yaml.safe_load(self.original):
            return self.original
        output = StringIO()
        YAML(typ="rt").dump(self.data, output)
        text = output.getvalue()
        if yaml.safe_load(text) != self.data:
            # MetaLad reads YAML 1.1. Quote ambiguous text such as the title "On".
            writer = YAML(typ="rt")
            writer.version = (1, 1)
            output = StringIO()
            writer.dump(self.data, output)
            text = output.getvalue()
        if len(text.encode()) > 1_000_000 or yaml.safe_load(text) != self.data:
            raise ValueError(f"{self.path}: record exceeds 1 MB or cannot round-trip")
        return text


def save_metadata(*documents):
    """Stage both files, detect stale edits and undo a partial write on I/O failure."""
    with ExitStack() as stack:
        pending = []
        for doc in sorted(documents, key=lambda item: item.path):
            key = hashlib.sha256(os.fsencode(doc.path)).hexdigest()
            lock = Path(tempfile.gettempdir(), f"shacl-py-{key}.lock")
            stack.enter_context(FileLock(lock, timeout=10))
            current = read_metadata(doc.path) if os.path.lexists(doc.path) else None
            if current != doc.original:
                raise ValueError(f"{doc.path}: changed during setup, please retry")
            updated = doc.serialise()
            if updated == current:
                continue
            staging = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(
                        dir=doc.path.parent, prefix=".shacl-py-"
                    )
                )
            )
            new = staging / "new"
            new.write_text(updated, encoding="utf-8")
            backup = None
            if current is not None:
                backup = staging / "original"
                os.link(doc.path, backup)
                new.chmod(doc.path.stat().st_mode)
            pending.append((doc.path, new, backup))
        done = []
        try:
            for target, new, backup in pending:
                if backup is None:
                    os.link(new, target)
                else:
                    new.replace(target)
                done.append((target, backup))
        except OSError:
            for target, backup in reversed(done):
                if backup is None:
                    target.unlink()
                else:
                    backup.replace(target)
            raise
        return {path for path, _, _ in pending}
