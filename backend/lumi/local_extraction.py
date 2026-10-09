"""Small CPU-only NLP pipeline. Relationships require literal source evidence."""

import hashlib
import re
import unicodedata
from functools import lru_cache
from itertools import combinations

from .config import settings

import spacy
from spacy.matcher import Matcher, PhraseMatcher

PIPELINE_VERSION = "pipeline-v4.1-local-nlp"
TERMS = (
    "knowledge graph",
    "knowledge graphs",
    "vector search",
    "embeddings",
    "embedding",
    "retrieval",
    "language model",
    "language models",
    "neural network",
    "machine learning",
    "SQLite",
    "NetworkX",
    "Neo4j",
    "Python",
    "API",
    "agents",
    "agent",
    "context window",
    "harness engineering",
    "prompt engineering",
)
STOP = {"document", "page", "figure", "table", "section", "example", "information", "thing", "way"}
RELATIONS = {
    "uses": "USES",
    "requires": "REQUIRES",
    "depends on": "REQUIRES",
    "is part of": "PART_OF",
    "implements": "IMPLEMENTS",
    "extends": "EXTENDS",
}


def normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", value.replace("–", "-").replace("‑", "-"))


@lru_cache(maxsize=1)
def engine():
    try:
        nlp = spacy.load(settings.spacy_model, disable=["parser"])
        name = f"{settings.spacy_model}-{nlp.meta.get('version', 'unknown')}"
    except OSError:
        nlp = spacy.blank("en")
        name = "rules-only (install en_core_web_sm for NER)"
    nlp.add_pipe("sentencizer")
    phrases = PhraseMatcher(nlp.vocab, attr="LOWER")
    phrases.add("TECHNICAL", list(nlp.tokenizer.pipe(TERMS)))
    nouns = Matcher(nlp.vocab)
    nouns.add(
        "NOUN_PHRASE",
        [[{"POS": "ADJ", "OP": "?"}, {"POS": {"IN": ["NOUN", "PROPN"]}, "OP": "{1,3}"}]],
    )
    return nlp, phrases, nouns, name


def version():
    return f"{PIPELINE_VERSION}:{engine()[3]}"


def extract(text, timings):
    nlp, phrases, nouns, name = engine()
    with timings.measure("entity_extraction"):
        doc = nlp(text)
        candidates = [
            (ent.start, ent.end, ent.label_)
            for ent in doc.ents
            if ent.label_ in {"PERSON", "ORG", "GPE", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW"}
        ]
        candidates += [(start, end, "TECHNICAL") for _, start, end in phrases(doc)]
        candidates += [
            (start, end, "CONCEPT")
            for _, start, end in (nouns(doc) if doc.has_annotation("POS") else [])
            if 1 <= end - start <= 4
        ]
        # Prefer longest spans; an occurrence belongs to one entity only.
        occupied, hits, keys = set(), [], set()
        for start, end, label in sorted(
            candidates, key=lambda item: (-(item[1] - item[0]), item[0])
        ):
            span = doc[start:end]
            key = normalize(span.text)
            # Repeated PDF navigation headings are page furniture, not entities.
            if len(re.findall(r"\b(?:section|chapter|figure|table|page)\s+\d+", key)) >= 2:
                continue
            if key in STOP or len(key) < 2 or len(key) > 100 or not any(c.isalpha() for c in key):
                continue
            if occupied.intersection(range(start, end)) or (key not in keys and len(keys) >= 24):
                continue
            occupied.update(range(start, end))
            keys.add(key)
            sentence = span.sent
            hits.append(
                dict(
                    key=key,
                    name=span.text,
                    label=label,
                    start=span.start_char,
                    end=span.end_char,
                    quote=sentence.text,
                    sentence_start=sentence.start_char,
                    sentence_end=sentence.end_char,
                )
            )
        hits.sort(key=lambda hit: hit["start"])
    with timings.measure("relationship_extraction"):
        edges = []
        by_sentence = {}
        for hit in hits:
            by_sentence.setdefault((hit["sentence_start"], hit["sentence_end"]), []).append(hit)
        for (start, end), group in by_sentence.items():
            quote = text[start:end]
            unique = list({hit["key"]: hit for hit in group}.values())[:8]
            for a, b in combinations(unique, 2):
                edges.append(
                    dict(
                        source=a["key"],
                        target=b["key"],
                        relation="CO_OCCURS_WITH",
                        quote=quote,
                        confidence=0.1,
                        kind="cooccurrence",
                        verified=False,
                        method="same_sentence",
                    )
                )
            # Conservative directed rules: exact subject + exact connecting verb.
            for a, b in zip(group, group[1:]):
                prefix = normalize(text[start : a["start"]])
                connector = normalize(text[a["end"] : b["start"]])
                suffix = text[b["end"] : end].strip()
                if prefix not in {"", "a", "an", "the"} or connector not in RELATIONS:
                    continue
                if re.search(
                    r"\b(?:not|never|may|might|could|if|unless|whether)\b|\?", quote, re.I
                ):
                    continue
                if (
                    suffix
                    and suffix[0] not in ".,;!"
                    and not re.match(r"(?:to|for)\b", suffix, re.I)
                ):
                    continue
                if a["key"] != b["key"]:
                    edges.append(
                        dict(
                            source=a["key"],
                            target=b["key"],
                            relation=RELATIONS[connector],
                            quote=quote,
                            confidence=1.0,
                            kind="semantic",
                            verified=True,
                            method="explicit_statement_rule",
                        )
                    )
    return dict(hits=hits, edges=edges, engine=name)


def cache_key(text):
    return hashlib.sha256((version() + "\0" + text).encode()).hexdigest()
