"""Project-selected record collections backed by local JSON Schemas."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable
from ruamel.yaml import YAML
from ruamel.yaml.constructor import SafeConstructor
from ruamel.yaml.error import YAMLError

from shacl_py.catalogue import record_validator
from shacl_py.files import read_metadata, scoped_path

CONFIG = ".shacl-py/config.yaml"
BUNDLED_TEMPLATES = Path(__file__).with_name("collection_templates")


def bundled_templates():
    return sorted(p.parent.name for p in BUNDLED_TEMPLATES.glob("*/template.yaml"))


def resolve_template(name_or_path):
    """Return a bundled template's directory for its name, otherwise the given path."""
    path = Path(name_or_path).expanduser()
    if not path.exists() and name_or_path in bundled_templates():
        return BUNDLED_TEMPLATES / name_or_path
    return path


class CatalogueConstructor(SafeConstructor):
    """Keep ISO dates as written for JSON Schema format validation."""


CatalogueConstructor.add_constructor(
    "tag:yaml.org,2002:timestamp", SafeConstructor.construct_scalar
)


def read_document(content):
    reader = YAML(typ="safe", pure=True)
    reader.Constructor = CatalogueConstructor
    try:
        value = reader.load(content)
        # Reject YAML-only values and cyclic aliases before validation or display.
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError, YAMLError) as error:
        raise ValueError(str(error)) from error


@dataclass
class Collection:
    key: str
    title: str
    label_field: str
    field_labels: dict[str, str]
    entries: dict[str, dict]
    context: dict
    presentation: dict
    project_root: Path | None
    groups: list = field(default_factory=list)

    @property
    def section(self):
        return f"collection/{self.key}"


def mapping(value, name):
    if not isinstance(value, dict):
        raise TypeError(f"{name}: expected a mapping")
    return value


def text_field(settings, name, default=None):
    value = settings.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: expected a non-empty string")
    return value


def collection_key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", key):
        raise ValueError(f"invalid collection ID {key!r} (use letters, digits, - or _)")
    return key


def read_template(path):
    if path.is_dir() and not path.is_symlink():
        path = path / "template.yaml"
    try:
        settings = mapping(read_document(read_metadata(path)), "template")
        collection_key(settings.get("id"))
        for field in ("example", "schema"):
            scoped_path(path.parent, text_field(settings, field))
        if "linkml" in settings:
            scoped_path(path.parent, text_field(settings, "linkml"))
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from error
    return path, settings


def template_assets(manifest, settings):
    names = [manifest.name, settings["schema"], settings["example"]]
    if "linkml" in settings:
        names.append(settings["linkml"])
    return names


def validate_document(schema_path, document, schema_text):
    try:
        schema = json.loads(
            schema_text if schema_text is not None else read_metadata(schema_path)
        )
        if not isinstance(schema, (dict, bool)):
            raise TypeError("expected a JSON Schema object or boolean")
        if isinstance(schema, dict) and "$schema" in schema:
            text_field(schema, "$schema")
            cls = validator_for(schema, default=None)
            if cls is None:
                raise ValueError(
                    f"unsupported JSON Schema dialect {schema['$schema']!r}"
                )
        else:
            cls = validator_for(schema)
        cls.check_schema(schema)
        # An empty registry resolves bundled references without network access.
        validator = cls(schema, registry=Registry(), format_checker=cls.FORMAT_CHECKER)
        issue = next(validator.iter_errors(document), None)
    except (OSError, ValueError, TypeError, SchemaError, Unresolvable) as error:
        raise ValueError(f"{schema_path}: {error}") from error
    if issue:
        raise ValueError(f"{issue.json_path}: {issue.message}")


def parse_collection(
    key, settings, schema_path, content, *, schema_text=None, project_root=None
):
    document = read_document(content)
    validate_document(schema_path, document, schema_text)
    title = text_field(settings, "title", key)
    id_field = text_field(settings, "id_field", "id")
    label_field = text_field(settings, "label_field", "name")
    labels = mapping(settings.get("field_labels", {}), "field_labels")
    for label_key in labels:
        text_field(labels, label_key)
    presentation = settings.get("presentation", {})
    if "presentation" in settings:
        issue = next(
            record_validator("collection-view").iter_errors(presentation), None
        )
        if issue:
            raise ValueError(f"presentation {issue.json_path}: {issue.message}")
    context = {}
    rows = document
    if "records" in settings:
        slot = text_field(settings, "records")
        mapping(document, "catalogue")
        rows = document.get(slot)
        context = {k: v for k, v in document.items() if k != slot}
    if not isinstance(rows, list):
        raise TypeError(
            f"{settings.get('records', 'catalogue')}: expected a list of records"
        )
    entries = {}
    for i, row in enumerate(rows):
        mapping(row, f"record [{i}]")
        identifier = row.get(id_field)
        if type(identifier) not in (str, int) or not str(identifier).strip():
            raise ValueError(f"record [{i}].{id_field}: expected a non-empty ID")
        identifier = str(identifier)
        if identifier in entries:
            raise ValueError(f"record [{i}].{id_field}: duplicate ID {identifier!r}")
        try:
            text_field(row, label_field)
        except ValueError as error:
            raise ValueError(f"record [{i}].{error}") from error
        entries[identifier] = row
    collection = Collection(
        key, title, label_field, labels, entries, context, presentation, project_root
    )
    if presentation:
        from shacl_py.collection_view import collection_groups

        if (
            presentation.get("source")
            and context.get(presentation["source"]) is not None
        ):
            mapping(context[presentation["source"]], presentation["source"])
        collection.groups = collection_groups(collection)
    return collection


def load_collections(root, *, only=None):
    """Load each configured collection independently and claim its data file."""
    collections, errors, paths = [], [], set()
    try:
        config = scoped_path(root, CONFIG)
        if not config.exists() and not config.is_symlink():
            return collections, errors, paths
        doc = read_document(read_metadata(config))
        settings = mapping({} if doc is None else doc, CONFIG)
        definitions = mapping(settings.get("collections", {}), "collections")
    except (OSError, TypeError, ValueError) as error:
        return [], [f"{root / CONFIG}: {error}"], paths
    for key, definition in definitions.items():
        if only is not None and (
            not isinstance(definition, dict)
            or not isinstance(definition.get("data"), str)
            or root / definition["data"] != only
        ):
            continue
        location = f"{config}: collections.{key}"
        try:
            collection_key(key)
            mapping(definition, "collection")
            data = scoped_path(root, text_field(definition, "data"))
            paths.add(data)
            location = f"{data} (collection {key})"
            base = root
            if "template" in definition:
                path, defaults = read_template(
                    scoped_path(root, text_field(definition, "template"))
                )
                if only is None:
                    paths.update(
                        path.parent / name for name in template_assets(path, defaults)
                    )
                if "schema" not in definition:
                    base = path.parent
                definition = defaults | definition
            schema = scoped_path(base, text_field(definition, "schema"))
            if only is None:
                paths.add(schema)
            collections.append(
                parse_collection(
                    key, definition, schema, read_metadata(data), project_root=root
                )
            )
        except (OSError, TypeError, ValueError) as error:
            errors.append(f"{location}: {error}")
    return collections, errors, paths
