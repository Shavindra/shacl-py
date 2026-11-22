"""A record-first detail view driven by the project's collection settings."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import quote

import yaml

from shacl_py.browser import doi_identifier, searchable
from shacl_py.files import inline_image, scoped_path
from shacl_py.sources import source_url


@dataclass
class Variant:
    entry: str
    key: str
    name: str
    category: str
    data: dict


@dataclass
class Group:
    entry: str
    name: str
    terms: list[str]
    members: dict = field(default_factory=dict)
    variants: list[Variant] = field(default_factory=list)
    starred: bool = False

    @property
    def variant_count(self):
        return len({v.category for v in self.variants})


def objects(record, key):
    return [v for v in (record.get(key) or []) if isinstance(v, dict)]


def collection_groups(collection):
    layout = collection.presentation
    terms_field = layout.get("terms", {}).get("field")
    variants = layout.get("variants")
    groups = {}
    for key, row in collection.entries.items():
        terms = row.get(terms_field) or []
        if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
            raise ValueError(f"{key}.{terms_field}: expected a list of term IDs")
        # A shared set of terms represents one concept. Unmapped records keep their own IDs.
        identity = tuple(sorted(set(terms))) if terms else key
        group = groups.setdefault(
            identity, Group(key, row[collection.label_field], terms)
        )
        group.members[key] = row
        group.starred |= row.get(layout.get("starred")) is True
        if variants:
            ids = set()
            for record in objects(row, variants["field"]):
                category = record.get(variants.get("group_field"))
                variant_id = record.get(variants["id_field"]) or category
                name = record.get(variants["label_field"])
                if (
                    not isinstance(variant_id, str)
                    or not variant_id
                    or not isinstance(name, str)
                    or not name
                ):
                    raise ValueError(
                        f"{key}.{variants['field']}: each entry needs a text ID and label"
                    )
                if category is not None and not isinstance(category, str):
                    raise ValueError(
                        f"{key}.{variants['group_field']}: expected a text group ID"
                    )
                if variant_id in ids:
                    raise ValueError(
                        f"{key}.{variants['field']}: duplicate record ID {variant_id!r}"
                    )
                ids.add(variant_id)
                group.variants.append(
                    Variant(key, variant_id, name, category or variant_id, record)
                )
    return sorted(
        groups.values(),
        key=lambda g: (not g.starred, "" if g.starred else g.name.casefold()),
    )


def href(value):
    if isinstance(value, str):
        try:
            return source_url(value)
        except ValueError:
            pass
    return None


def reference_data(ref):
    doi = ref.get("doi") or ""
    return dict(ref, doi=doi, href=href(ref.get("url")) or href(doi))


def references_in(group, layout):
    key = layout.get("references")
    for entry, row in group.members.items():
        for ref in objects(row, key):
            yield entry, None, ref
    for variant in group.variants:
        for ref in objects(variant.data, key):
            yield variant.entry, variant.key, ref


def matches(group, collection, term):
    layout = collection.presentation
    values = [group.name, *group.terms, *group.members]
    for row in group.members.values():
        values.extend([row.get(layout.get("aliases")), row[collection.label_field]])
    values.extend(
        ref.get("doi") or ref.get("url") for _, _, ref in references_in(group, layout)
    )
    for spec in layout.get("sections", []):
        if "lookup" in spec:
            rows = (
                [v.data for v in group.variants]
                if spec.get("scope") == "variant"
                else group.members.values()
            )
            for row in rows:
                linked = section_value(collection, spec, row)
                for item in linked if isinstance(linked, list) else []:
                    if isinstance(item, dict):
                        values.extend(
                            ref.get("doi") or ref.get("url")
                            for ref in objects(item, layout.get("references"))
                        )
    return term in searchable(values)


def reference_page(unassigned, groups, layout):
    counts = Counter(
        doi_identifier(ref.get("doi") or ref.get("url")) for ref in unassigned
    )
    counts.pop(None, None)
    cited = defaultdict(list)
    for group in groups:
        for entry, variant, ref in references_in(group, layout):
            doi = doi_identifier(ref.get("doi") or ref.get("url"))
            target = (group.name, entry, variant)
            if doi and target not in cited[doi]:
                cited[doi].append(target)
    rows = []
    for ref in unassigned:
        doi = doi_identifier(ref.get("doi") or ref.get("url"))
        rows.append(
            dict(reference_data(ref), occurrences=counts[doi], cited_by=cited[doi])
        )
    return {"rows": rows, "distinct": len(counts)}


def image_data(record, root, scope):
    location = record.get("path")
    remote = href(record.get("url"))
    preview = None
    if location and root:
        try:
            preview = inline_image(scoped_path(root, location), root)
        except TypeError, ValueError:
            pass
    return dict(
        record,
        preview=preview or remote,
        remote=remote,
        scope=scope,
        source_href=href(record.get("source_reference")),
    )


def section_value(collection, spec, row):
    value = row.get(spec["field"])
    lookup = spec.get("lookup")
    if not lookup or not isinstance(value, list):
        return value
    index = {
        r.get(lookup["id_field"]): r
        for r in objects(collection.context, lookup["table"])
        if isinstance(r.get(lookup["id_field"]), (str, int))
    }
    return [index.get(k, k) if isinstance(k, (str, int)) else k for k in value]


def extra_sections(collection, row, variant):
    sections = []
    for spec in collection.presentation.get("sections", []):
        data = (
            (variant.data if variant else {}) if spec.get("scope") == "variant" else row
        )
        value = section_value(collection, spec, data)
        if value is not None and value != [] and value != "":
            sections.append((spec["label"], value))
    return sections


def concept_notes(collection, group):
    """Collect distinct general notes from every record for the selected concept."""
    spec = collection.presentation.get("notes")
    if not spec:
        return []
    notes = [
        note for row in group.members.values() for note in objects(row, spec["field"])
    ]
    fields = []
    for key in spec["fields"]:
        values = []
        for note in notes:
            text = note.get(key)
            if isinstance(text, str) and text.strip() and text not in values:
                values.append(text)
        if values:
            fields.append((collection.field_labels.get(key, key), values))
    return fields


def variant_tabs(variants):
    counts = Counter(v.category for v in variants)
    seen = Counter()
    tabs = []
    for v in variants:
        seen[v.category] += 1
        label = f"{v.name} {seen[v.category]}" if counts[v.category] > 1 else v.name
        tabs.append((v, label))
    return tabs


def detail_view(collection, params):
    layout = collection.presentation
    groups = collection.groups
    scope = {"section": collection.section}
    scope.update({k: params[k] for k in ("q", "filter", "tag") if params.get(k)})
    query = params.get("q", "").strip().casefold()
    term = params.get("filter", "").strip().casefold()
    shown = [
        g
        for g in groups
        if (scope.get("tag") != "starred" or g.starred)
        and (not query or query in searchable(g.members))
        and (not term or matches(g, collection, term))
    ]
    entry = params.get("entry")
    group = (
        next((g for g in shown if entry in g.members), None)
        if entry
        else next(iter(shown), None)
    )
    unassigned = objects(collection.context, layout.get("unassigned_references"))
    result = {
        "scope": scope,
        "shown": shown,
        "group": group,
        "unassigned_count": len(unassigned),
    }
    if params.get("panel") == "unassigned" and "unassigned_references" in layout:
        return result | {"reference_page": reference_page(unassigned, groups, layout)}
    if not group:
        return result
    entry = entry or group.entry
    variant = next(
        (
            v
            for v in group.variants
            if v.entry == entry and v.key == params.get("variant")
        ),
        None,
    )
    missing_variant = "variant" in params and variant is None
    if variant is None and not missing_variant:
        variant = next((v for v in group.variants if v.entry == entry), None)
    if variant:
        entry = variant.entry
    row = group.members[entry]
    data = variant.data if variant else row
    owners = [(row, "Shared" if variant else "")]
    if variant:
        owners.append((variant.data, ""))
    source = collection.context.get(layout.get("source")) or {}
    terms = layout.get("terms", {})
    term_links = [
        (t, href(terms.get("url", "").replace("{id}", quote(t, safe=":"))))
        for t in group.terms
    ]
    result.update(
        entry=entry,
        variant=variant,
        row=row,
        terms=term_links,
        tabs=variant_tabs(group.variants),
        notes=concept_notes(collection, group),
        missing_variant=missing_variant,
        variant_context=[
            (collection.field_labels.get(k, k), data[k])
            for k in layout.get("variants", {}).get("context_fields", [])
            if data.get(k)
        ],
        route=scope | {"entry": entry, "variant": variant.key if variant else None},
        definition=row.get(terms.get("definition")),
        summary=row.get(layout.get("summary")),
        source=source,
        source_href=href(source.get("url")),
        overview=[
            (collection.field_labels.get(k, k), data.get(k)) for k in layout["overview"]
        ],
        sections=extra_sections(collection, row, variant),
        references=[
            dict(reference_data(r), scope=label)
            for owner, label in owners
            for r in objects(owner, layout.get("references"))
        ],
        images=[
            image_data(i, collection.project_root, label)
            for owner, label in owners
            for i in objects(owner, layout.get("images"))
        ],
    )
    if params.get("view") == "raw":
        result["raw"] = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        if variant:
            result["full_record"] = yaml.safe_dump(
                row, allow_unicode=True, sort_keys=False
            )
        result["catalogue_raw"] = yaml.safe_dump(
            collection.context, allow_unicode=True, sort_keys=False
        )
    return result
