"""MetaLad StudyMiniMeta input belongs to the containing DataLad dataset."""

from datalad_metalad.extractors.studyminimeta.ldcreator import LDCreator


def dataset_root(folder):
    return next(
        (p for p in (folder, *folder.parents) if (p / ".datalad/config").is_file()),
        folder,
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
