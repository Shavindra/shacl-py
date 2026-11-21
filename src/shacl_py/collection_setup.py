"""Install a local collection template and register its catalogue."""

import os
from dataclasses import dataclass
from pathlib import Path

from shacl_py.collection import (
    CONFIG,
    mapping,
    parse_collection,
    read_document,
    read_template,
    template_assets,
)
from shacl_py.files import read_metadata, scoped_path
from shacl_py.metadata_io import MetadataFile, save_metadata


@dataclass
class TemplateFile:
    path: Path
    original: str | None
    content: str

    def serialise(self):
        return self.content


def original_text(path):
    return read_metadata(path) if os.path.lexists(path) else None


def setup_collection(root, template, data=None):
    if not root.is_dir():
        raise ValueError(f"{root}: expected an existing project directory")
    manifest, settings = read_template(template.absolute())
    manifest = manifest.resolve()
    key = settings["id"]
    config = MetadataFile.read(scoped_path(root, CONFIG))
    collections = mapping(config.data.setdefault("collections", {}), "collections")
    bundle = (
        manifest.parent
        if manifest.is_relative_to(root)
        else root / ".shacl-py/templates" / key
    )
    template_path = (bundle / manifest.name).relative_to(root).as_posix()
    example = scoped_path(manifest.parent, settings["example"])
    data_path = scoped_path(
        root, data if data is not None else f"collections/{key}{example.suffix}"
    )
    declaration = {
        "template": template_path,
        "data": data_path.relative_to(root).as_posix(),
    }
    if key in collections and collections[key] != declaration:
        raise ValueError(
            f"{config.path}: collection {key!r} already has different settings"
        )
    collections[key] = declaration

    # Copy only the assets declared by the template. An in-project template is
    # registered in place. All existing files participate in the stale-edit check.
    files = {}
    for name in template_assets(manifest, settings):
        source = scoped_path(manifest.parent, name)
        target = scoped_path(root, (bundle / name).relative_to(root).as_posix())
        content = read_metadata(source)
        original = original_text(target)
        if original is not None and original != content:
            raise ValueError(f"{target}: existing template file differs")
        files[target] = TemplateFile(target, original, content)
    if read_document(files[bundle / manifest.name].content) != settings:
        raise ValueError(f"{manifest}: changed during setup, please retry")
    if data_path in files or config.path in files or data_path == config.path:
        raise ValueError(
            "the data file, project settings and template assets must have separate paths"
        )
    original = original_text(data_path)
    content = (
        files[bundle / settings["example"]].content if original is None else original
    )
    files[data_path] = TemplateFile(data_path, original, content)
    try:
        schema = files[bundle / settings["schema"]]
        collection = parse_collection(
            key, settings, schema.path, content, schema_text=schema.content
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"{data_path}: {error}") from error
    for path in [*files, config.path]:
        path.parent.mkdir(parents=True, exist_ok=True)
    save_metadata(config, *files.values())
    print(
        f"{collection.title}: registered {len(collection.entries)} record(s) from {declaration['data']}."
    )
