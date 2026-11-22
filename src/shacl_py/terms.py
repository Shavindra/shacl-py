"""Index individual terms and the subject–property relationships a record declares."""

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property

from shacl_py.catalogue import Catalogue
from shacl_py.graph import KEYWORD_FIELDS, SUBJECT_FIELDS, metadata_labels

ROLES = ("subject", "property", "keyword")


def words(text):
    return frozenset(re.findall(r"[^\W_]+", text.casefold()) or text.strip().split())


@dataclass(frozen=True)
class TermQuery:
    clauses: list
    scoped: bool


@dataclass(frozen=True)
class Term:
    id: str
    label: str
    role: str
    category: str
    aliases: tuple = ()
    broader: Term | None = None

    def lineage(self):
        term = self
        while term:
            yield term
            term = term.broader

    @property
    def names(self):
        return (self.label, *self.aliases)

    @property
    def route(self):
        key = "term" if self.role == "property" else self.role
        return {"section": "terms", key: self.id}


@dataclass(frozen=True)
class Topic:
    subject: Term | None
    value: Term | None
    note: str = ""

    @property
    def terms(self):
        return tuple(t for t in (self.subject, self.value) if t)

    @cached_property
    def tokens(self):
        return words(
            " ".join(
                name
                for t in self.terms
                for parent in t.lineage()
                for name in parent.names
            )
        )

    def matches(self, query, subject="", prop=""):
        if subject and (
            not self.subject or subject not in (t.id for t in self.subject.lineage())
        ):
            return False
        if prop and (
            not self.value
            or self.value.role != "property"
            or prop not in (t.id for t in self.value.lineage())
        ):
            return False
        return any(
            tokens <= self.tokens
            and (
                not subjects
                or self.subject
                and any(t.id in subjects for t in self.subject.lineage())
                or not self.subject
                and tokens == self.tokens
            )
            for subjects, tokens in query.clauses
        )


def resolve(vocabulary, key, default_role=None):
    chain = []
    while key:
        definition = vocabulary[key]
        chain.append(definition)
        key = definition.get("broader")
    role = next((d["role"] for d in chain if "role" in d), default_role)
    if role is None:
        return None
    parent = None
    for definition in reversed(chain):
        parent = Term(
            definition["id"],
            definition["label"],
            role,
            definition.get("category", parent.category if parent else role.title()),
            tuple(definition.get("aliases", [])),
            parent,
        )
    return parent


def record_topics(fields, vocabulary):
    if vocabulary is not None:
        subjects = set()
        for entry in fields.get("index_terms", []):
            subject = (
                resolve(vocabulary, entry["subject"], "subject")
                if "subject" in entry
                else None
            )
            key = entry.get("property", entry.get("term"))
            value = resolve(vocabulary, key, "property") if key else None
            if value and value.role == "subject":
                subject, value = value, None
            if subject:
                subjects.add(subject.id)
            yield Topic(subject, value, entry.get("note", ""))

        # A direct subject statement indexes the subject on its own. Nested
        # statements describe other records, such as a file, and have their own scope.
        for statement in fields.get("characterized_by", []):
            key = statement.get("object")
            if (
                statement.get("predicate") in SUBJECT_FIELDS
                and isinstance(key, str)
                and key in vocabulary
                and key not in subjects
            ):
                term = resolve(vocabulary, key)
                if term and term.role == "subject":
                    subjects.add(key)
                    yield Topic(term, None)

    for label in metadata_labels(fields, KEYWORD_FIELDS):
        yield Topic(
            None, Term("keyword/" + label.casefold(), label, "keyword", "Keyword")
        )


def grouped_terms(terms):
    groups = defaultdict(list)
    for term in sorted(
        terms,
        key=lambda t: (
            ROLES.index(t.role),
            t.category.casefold(),
            t.label.casefold(),
            t.id,
        ),
    ):
        groups[term.category].append(term)
    return groups


def topic_terms(topics):
    return {
        (term.role, term.id): term for topic in topics for term in topic.terms
    }.values()


class TermIndex:
    def __init__(self, items, key_for):
        self.by_record = defaultdict(dict)
        self.records = {}
        self.facets = {role: {} for role in ROLES}
        self.subject_names = defaultdict(set)
        self.term_names = set()
        vocabularies = {}
        for item in items:
            if not (item.is_publication or item.is_dataset):
                continue
            if item.ref not in vocabularies:
                vocabularies[item.ref] = (
                    {d["id"]: d for d in item.source.data.get("term_vocabulary", [])}
                    if isinstance(item.source, Catalogue)
                    else None
                )
            key = key_for(item)
            for topic in record_topics(item.fields, vocabularies[item.ref]):
                identity = tuple((t.role, t.id) for t in topic.terms), topic.note
                self.by_record[key].setdefault(identity, topic)
                if key not in self.records or item.fields.get("index_terms"):
                    self.records[key] = item
                for term in topic.terms:
                    for ancestor in term.lineage():
                        self.facets[ancestor.role].setdefault(ancestor.id, ancestor)
                        if ancestor.role == "subject":
                            for name in ancestor.names:
                                if name.strip():
                                    self.subject_names[words(name)].add(ancestor.id)
                        elif ancestor.role == "property":
                            self.term_names.update(
                                words(name) for name in ancestor.names if name.strip()
                            )

    def topics(self, key):
        return self.by_record.get(key, {}).values()

    def filters(self):
        for role, choices in self.facets.items():
            if choices:
                groups = grouped_terms(choices.values())
                label = (
                    next(iter(groups))
                    if role == "subject" and len(groups) == 1
                    else role.title()
                )
                yield "term" if role == "property" else role, label, groups

    def query(self, text):
        clauses = []
        subjects = set()
        scoped = True
        for part in re.split(r"\s+or\s+", text.strip(), flags=re.IGNORECASE):
            tokens = words(part)
            names = [name for name in self.subject_names if name <= tokens]
            property_words = tokens
            if names:
                # A longer subject name takes precedence over a shorter alias.
                length = max(map(len, names))
                longest = [name for name in names if len(name) == length]
                subjects = set().union(*(self.subject_names[n] for n in longest))
                property_words = tokens.difference(*longest)
            scoped = scoped and bool(subjects and property_words in self.term_names)
            clauses.append((subjects, tokens))
        return TermQuery(clauses, scoped)

    def results(self, query, subject, term, is_starred, *, keyword=""):
        groups = {"Papers": [], "Datasets": []}
        parsed = self.query(query)
        for key, item in self.records.items():
            topics = self.topics(key)
            if keyword:
                keywords = [
                    t
                    for t in topics
                    if t.value and t.value.role == "keyword" and t.value.id == keyword
                ]
                if not keywords:
                    continue
                if not (query or subject or term):
                    topics = keywords
            matches = [t for t in topics if t.matches(parsed, subject, term)]
            if matches:
                group = groups["Papers" if item.is_publication else "Datasets"]
                group.append((item, matches))
        for group in groups.values():
            group.sort(
                key=lambda row: (not is_starred(row[0]), row[0].label.casefold())
            )
        return groups
