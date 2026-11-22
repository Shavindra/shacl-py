"""Look up authored terms for papers and datasets, including alternate descriptions."""

import re
from collections import defaultdict
from dataclasses import dataclass

from shacl_py.catalogue import Catalogue
from shacl_py.graph import KEYWORD_FIELDS, metadata_labels


def words(text):
    return frozenset(re.findall(r"[^\W_]+", text.casefold()) or text.strip().split())


@dataclass(frozen=True)
class TermQuery:
    clauses: list
    scoped: bool


@dataclass(frozen=True)
class Topic:
    subject: str
    subject_label: str
    term: str
    label: str
    broader: tuple
    tokens: frozenset
    note: str = ""

    @property
    def pair(self):
        return self.subject, self.term

    def matches(self, query, subject="", term=""):
        return (
            (not subject or subject == self.subject)
            and (not term or term == self.term or term in self.broader)
            and any(
                tokens <= self.tokens
                and (
                    not subjects
                    or self.subject in subjects
                    or not self.subject
                    and tokens == self.tokens
                )
                for subjects, tokens in query.clauses
            )
        )


def names(definition):
    return [definition["label"], *definition.get("aliases", [])]


def record_topics(fields, vocabulary):
    assignments = fields.get("index_terms", []) if vocabulary is not None else ()
    for entry in assignments:
        key = entry["term"]
        definition = vocabulary[key]
        subject = entry.get("subject", "")
        subject_label = vocabulary[subject]["label"] if subject else ""
        labels = names(vocabulary[subject]) if subject else []
        labels.extend(names(definition))
        parents = []
        while parent := definition.get("broader"):
            parents.append(parent)
            definition = vocabulary[parent]
            labels.extend(names(definition))
        yield Topic(
            subject,
            subject_label,
            key,
            vocabulary[key]["label"],
            tuple(parents),
            words(" ".join(labels)),
            entry.get("note", ""),
        )

    for label in metadata_labels(fields, KEYWORD_FIELDS):
        yield Topic("", "", "keyword/" + label.casefold(), label, (), words(label))


class TermIndex:
    def __init__(self, items, key_for):
        self.by_record = defaultdict(dict)
        self.records = {}
        self.subjects = {}
        self.terms = {}
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
            vocabulary = vocabularies[item.ref]
            key = key_for(item)
            for topic in record_topics(item.fields, vocabulary):
                self.by_record[key].setdefault(
                    (topic.subject, topic.term, topic.note), topic
                )
                if key not in self.records or item.fields.get("index_terms"):
                    self.records[key] = item
                if topic.subject:
                    self.subjects[topic.subject] = topic.subject_label
                    for name in names(vocabulary[topic.subject]):
                        if name.strip():
                            self.subject_names[words(name)].add(topic.subject)
                self.terms.setdefault(topic.term, topic.label)
                if vocabulary and topic.term in vocabulary:
                    self.term_names.update(
                        words(name) for name in names(vocabulary[topic.term])
                    )
                for parent in topic.broader:
                    self.terms[parent] = vocabulary[parent]["label"]
                    self.term_names.update(
                        words(name) for name in names(vocabulary[parent])
                    )

    def topics(self, key):
        return self.by_record.get(key, {}).values()

    def query(self, text):
        clauses = []
        subjects = set()
        scoped = True
        for part in re.split(r"\s+or\s+", text.strip(), flags=re.IGNORECASE):
            tokens = words(part)
            names = [name for name in self.subject_names if name <= tokens]
            property_words = tokens
            if names:
                # "Nuclear envelope" is more specific than the alias "nuclear".
                length = max(map(len, names))
                longest = [name for name in names if len(name) == length]
                subjects = set().union(*(self.subject_names[n] for n in longest))
                property_words = tokens.difference(*longest)
            scoped = scoped and bool(subjects and property_words in self.term_names)
            # An unnamed alternative shares the previous subject, e.g. "nucleus size or location".
            clauses.append((subjects, tokens))
        return TermQuery(clauses, scoped)

    def results(self, query, subject, term, is_starred):
        groups = {"Papers": [], "Datasets": []}
        query_words = self.query(query)
        for key, item in self.records.items():
            matches = [
                t for t in self.topics(key) if t.matches(query_words, subject, term)
            ]
            if matches:
                group = groups["Papers" if item.is_publication else "Datasets"]
                group.append((item, matches))
        for group in groups.values():
            group.sort(
                key=lambda row: (not is_starred(row[0]), row[0].label.casefold())
            )
        return groups
