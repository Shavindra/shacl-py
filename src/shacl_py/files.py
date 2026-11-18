"""Read-only access to declared project paths."""

import os
import stat
from pathlib import Path, PureWindowsPath

FILE_PATTERN_SLOTS = ("data_file_patterns", "dataset_file_patterns")
IGNORED = {".git", ".datalad", ".venv", "venv", "__pycache__", ".pytest_cache"}


def read_metadata(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("metadata must be a regular local file")
    if path.stat().st_size > 1_000_000:
        raise ValueError("metadata exceeds 1 MB")
    return path.read_text(encoding="utf-8")


def _paths_below(base: Path, *, skip_hidden_dirs: bool):
    if base.is_symlink() or not base.is_dir():
        return
    for directory, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and not (skip_hidden_dirs and d.startswith("."))
            and not Path(directory, d).is_symlink()
        )
        for name in sorted(files):
            yield Path(directory, name)


def in_git_tree(base):
    return any((directory / ".git").exists() for directory in (base, *base.parents))


def _available(path, check_pointers):
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return False
        if path.is_symlink() or not check_pointers or not 16 <= info.st_size <= 32768:
            return True
        # An unlocked, unmaterialised git-annex file can be a tiny pointer.
        # Only inspect its prefix unless it actually resembles a pointer.
        with path.open("rb", buffering=0) as stream:
            prefix = stream.read(15)
            if prefix != b"/annex/objects/" and not prefix.startswith(
                (b"../", b".git/")
            ):
                return True
            lines = (prefix + stream.read(32769 - len(prefix))).splitlines(
                keepends=True
            )
        first = lines[0].rstrip(b"\\r\\n")
        if first.startswith(b"/annex/objects/"):
            key = first.removeprefix(b"/annex/objects/")
        elif b".git/annex/objects/" in first:
            key = first.rsplit(b"/", 1)[-1]
        else:
            return True
        return not (
            b"--" in key
            and b"/" not in key
            and all(b"/annex/" in line and line.endswith(b"\\n") for line in lines[1:])
        )
    except OSError:
        return False


def _file_row(path, relative, check_pointers=False):
    return {
        "Filename": path.name,
        "Relative path": relative,
        "Availability": "Available"
        if _available(path, check_pointers)
        else "Unavailable",
    }


def scoped_path(base: Path, value: str) -> Path:
    """Resolve a literal path, without traversing symlink directories or Git internals."""
    if not isinstance(value, str):
        raise TypeError(f"expected a relative path, got {value!r}")
    path = Path(value)
    if (
        not value.strip()
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or any(part in IGNORED for part in path.parts)
    ):
        raise ValueError(f"expected a project-relative path, got {value!r}")
    current = base
    for part in path.parts:
        if current.is_symlink():
            raise ValueError(f"{value}: cannot traverse a symlink directory")
        current = current / part
    return current


def local_path(base: Path, value: str, *, directory=False) -> Path:
    current = scoped_path(base, value)
    if directory:
        if current.is_symlink() or not current.is_dir():
            raise ValueError(f"{value}: expected a local directory")
    elif current.is_symlink() and current.is_dir():
        raise ValueError(f"{value}: cannot traverse a symlink directory")
    elif not (current.is_file() or current.is_dir() or current.is_symlink()):
        raise ValueError(f"{value}: file or folder does not exist")
    return current


def folder_listing(base, relative):
    if any(part.startswith(".") for part in Path(relative).parts):
        raise ValueError("Select a visible folder within this record.")
    directory = local_path(base, relative, directory=True)
    folders, rows = [], []
    check_pointers = in_git_tree(base)
    for path in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
        if path.name in IGNORED or path.name.startswith("."):
            continue
        name = path.relative_to(base).as_posix()
        if path.is_dir():
            if not path.is_symlink():
                folders.append(name)
        elif path.is_file() or path.is_symlink():
            rows.append(_file_row(path, name, check_pointers))
    return folders, rows


def grouped_files(root, entity):
    """Enumerate only the explicitly selected folders. A literal file is also valid."""
    base = local_path(root, entity.get("local_folder", "."), directory=True)
    result = []
    check_pointers = in_git_tree(base)
    for group in entity.get("file_groups", []):
        rows = {}
        for selection in group["paths"]:
            path = local_path(base, selection)
            members = (
                _paths_below(path, skip_hidden_dirs=True) if path.is_dir() else [path]
            )
            for member in members:
                if member.name.casefold() in {".gitkeep", ".keep", ".ds_store", ".git"}:
                    continue
                relative = member.relative_to(base).as_posix()
                rows[relative] = _file_row(member, relative, check_pointers)
        result.append((group, [rows[key] for key in sorted(rows)]))
    return result
