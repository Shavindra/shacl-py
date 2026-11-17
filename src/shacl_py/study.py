"""MetaLad StudyMiniMeta input belongs to the containing DataLad dataset."""

from datalad_metalad.extractors.studyminimeta.ldcreator import LDCreator

from shacl_py.metadata_io import MetadataFile
from shacl_py.sources import source_url


def dataset_root(folder):
    return next(
        (p for p in (folder, *folder.parents) if (p / ".datalad/config").is_file()),
        folder,
    )


def read_study(path):
    data = MetadataFile.read(path).data
    if data:
        validate_study({"person": {}, **data}, path)
    return data


def publication_info(data, url=None):
    publications = data.get("publication", [])
    if len(publications) == 1:
        return publications[0]
    return next(
        (
            p
            for p in publications
            if url and p.get("doi") and source_url(p["doi"]) == url
        ),
        {},
    )


def validate_study(data, path):
    try:
        for key, kind in (
            ("study", dict),
            ("dataset", dict),
            ("person", dict),
            ("publication", list),
        ):
            if key in data and not isinstance(data[key], kind):
                raise ValueError(f"{key}: expected {kind.__name__}")
        if "person" not in data:
            raise ValueError("person: supply a mapping (use {} for no known people)")
        for section in ("study", "dataset"):
            for key in ("name", "description", "location", "purpose"):
                if key in data.get(section, {}) and not isinstance(
                    data[section][key], str
                ):
                    raise ValueError(f"{section}.{key}: expected text")
        for section, values in [
            ("dataset", data.get("dataset", {})),
            ("study", data.get("study", {})),
            *[
                (f"publication[{i}]", item)
                for i, item in enumerate(data.get("publication", []))
            ],
        ]:
            if not isinstance(values, dict):
                raise TypeError(f"{section}: expected a mapping")
            for key in ("keyword", "author", "contributor", "funding", "standard"):
                if key in values and not (
                    isinstance(values[key], list)
                    and all(isinstance(v, str) for v in values[key])
                ):
                    raise ValueError(
                        f"{section}.{key}: expected a list of names or identifiers"
                    )
        result = LDCreator("validation", "working-tree", path.name).create_ld_from_spec(
            data
        )
        if not result.success:
            raise ValueError(", ".join(result.messages))
    except (ValueError, TypeError, AttributeError, KeyError) as error:
        raise ValueError(f"{path}: {error}") from error


def person_names(people, ids):
    names = []
    for key in ids:
        person = people.get(key, {})
        name = " ".join(
            str(person.get(k, "")) for k in ("given_name", "last_name")
        ).strip()
        names.append(name or key)
    return names
