"""Offline structured Arabic citation and bibliography intelligence.

This module intentionally separates syntax extraction, bibliography linking, and
source-text verification. A linked bibliography entry is never treated as proof
that a lexical match originated from that source.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from plagiarism_detector.preprocessing.normalizer import normalize_light

_ARABIC_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
_YEAR_RE = r'(?:1[89]|20)[0-9٠-٩]{2}'
_AUTHOR_YEAR_RE = re.compile(
    rf'(?P<authors>[\u0600-\u06FFA-Za-z][\u0600-\u06FFA-Za-z\s\.\-&]{{1,70}})\s*[,،]\s*(?P<year>{_YEAR_RE})(?:\s*[,،]\s*(?:ص\.?|صفحة|p\.?|pp\.?)\s*(?P<pages>[0-9٠-٩\-–]+))?'
)
_NARRATIVE_RE = re.compile(
    rf'(?:أكد|يرى|أوضح|أشار|ذكر|حسب|وفقاً\s+ل(?:ـ)?)\s+(?P<authors>[\u0600-\u06FFA-Za-z][\u0600-\u06FFA-Za-z\s\.\-&]{{1,45}}?)\s*\(\s*(?P<year>{_YEAR_RE})\s*\)'
)
_NUMERIC_RE = re.compile(r'\[(?P<refs>[0-9٠-٩\s,،;؛\-]+)(?:[,،]\s*(?:ص\.?|صفحة|p\.?|pp\.?)\s*(?P<pages>[0-9٠-٩\-–]+))?\]')
_DOI_RE = re.compile(r'\b(?:doi\s*:\s*)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b', re.I)
_URL_RE = re.compile(r'https?://\S+', re.I)
_REFERENCE_NUMBER_RE = re.compile(r'^\s*[\[(]?(?P<number>[0-9٠-٩]{1,3})[\])]?[\.\-،,]?\s*')


@dataclass(frozen=True)
class CitationOccurrence:
    text: str
    start: int
    end: int
    citation_type: str
    authors: tuple[str, ...]
    year: str | None
    pages: str | None
    reference_numbers: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class BibliographyEntry:
    entry_id: str
    original_text: str
    segment_index: int
    start: int
    end: int
    reference_number: str | None
    authors: tuple[str, ...]
    year: str | None
    title: str | None
    publisher: str | None
    journal: str | None
    volume_issue: str | None
    page_range: str | None
    doi: str | None
    url: str | None
    confidence: float


def _digits(value: str | None) -> str | None:
    return value.translate(_ARABIC_DIGITS) if value else None


def normalize_author_name(value: str) -> str:
    """Conservative author key; it does not infer a person from incomplete text."""
    clean = re.sub(r'\b(?:دكتور|د\.?|dr\.?)\b', ' ', value, flags=re.I)
    clean = re.sub(r'[^\u0600-\u06FFA-Za-z\s]', ' ', clean)
    return ' '.join(normalize_light(clean).split())


def _author_keys(value: str) -> tuple[str, ...]:
    value = _REFERENCE_NUMBER_RE.sub('', value)
    # Arabic waw is a letter inside many surnames (for example: درويش), so
    # treat it as a separator only when it is a standalone conjunction.
    pieces = re.split(r'\s+(?:و|and)\s+|\s*&\s*|\s*[,،]\s*', value, flags=re.I)
    keys = [normalize_author_name(piece) for piece in pieces]
    return tuple(key for key in keys if key)


def _citation_dict(item: CitationOccurrence) -> dict[str, Any]:
    result = asdict(item)
    result['authors'] = list(item.authors)
    result['reference_numbers'] = list(item.reference_numbers)
    return result


def extract_citations(text: str) -> list[dict[str, Any]]:
    """Extract common author-year, narrative, and numeric citations with offsets."""
    if not text:
        return []
    found: list[CitationOccurrence] = []
    occupied: list[tuple[int, int]] = []
    for bracket in re.finditer(r'\((?P<body>[^()]{3,180})\)', text):
        body_start = bracket.start('body')
        for match in _AUTHOR_YEAR_RE.finditer(bracket.group('body')):
            start, end = body_start + match.start(), body_start + match.end()
            found.append(CitationOccurrence(
                text=text[start:end], start=start, end=end, citation_type='author_year',
                authors=_author_keys(match.group('authors')), year=_digits(match.group('year')),
                pages=_digits(match.group('pages')), reference_numbers=(), confidence=.90,
            ))
            occupied.append((start, end))
    for match in _NUMERIC_RE.finditer(text):
        refs = tuple(item for item in re.findall(r'[0-9٠-٩]{1,3}', match.group('refs')) if item)
        if refs:
            found.append(CitationOccurrence(
                text=match.group(0), start=match.start(), end=match.end(), citation_type='numeric',
                authors=(), year=None, pages=_digits(match.group('pages')),
                reference_numbers=tuple(_digits(item) or item for item in refs), confidence=.85,
            ))
            occupied.append((match.start(), match.end()))
    for match in _NARRATIVE_RE.finditer(text):
        if any(match.start() >= start and match.end() <= end for start, end in occupied):
            continue
        found.append(CitationOccurrence(
            text=match.group(0), start=match.start(), end=match.end(), citation_type='narrative_author_year',
            authors=_author_keys(match.group('authors')), year=_digits(match.group('year')),
            pages=None, reference_numbers=(), confidence=.78,
        ))
    return [_citation_dict(item) for item in sorted(found, key=lambda item: (item.start, item.end, item.citation_type))]


def parse_bibliography_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse bibliography-marked segment text without fabricating absent fields."""
    entries: list[BibliographyEntry] = []
    for segment_index, segment in enumerate(segments):
        if not segment.get('is_bibliography'):
            continue
        text = segment.get('text', '')
        if not text.strip() or re.match(r'^\s*(?:قائمة|ثبت|فهرس|المراجع|المصادر|references|bibliography)', text, re.I):
            continue
        number_match = _REFERENCE_NUMBER_RE.match(text)
        reference_number = _digits(number_match.group('number')) if number_match else None
        year_match = re.search(_YEAR_RE, text)
        year = _digits(year_match.group(0)) if year_match else None
        prefix = text[:year_match.start()].strip(' .،,;؛') if year_match else ''
        authors = _author_keys(prefix) if prefix else ()
        remainder = text[year_match.end():].strip(' .،,;؛') if year_match else ''
        parts = [part.strip() for part in re.split(r'[\.،,;؛]', remainder) if part.strip()]
        title = parts[0] if parts else None
        publisher = parts[1] if len(parts) > 1 else None
        doi_match = _DOI_RE.search(text)
        url_match = _URL_RE.search(text)
        page_match = re.search(r'(?:ص\.?|pp?\.?)\s*([0-9٠-٩]+\s*[-–]\s*[0-9٠-٩]+)', text, re.I)
        volume_match = re.search(r'(?:المجلد|vol\.?|عدد|issue)\s*([0-9٠-٩]+(?:\s*\(?[0-9٠-٩]+\)?)?)', text, re.I)
        confidence = .35 + (.20 if authors else 0) + (.20 if year else 0) + (.15 if title else 0) + (.10 if reference_number else 0)
        entries.append(BibliographyEntry(
            entry_id=f'bib:{segment_index}:{len(entries)}', original_text=text, segment_index=segment_index,
            start=0, end=len(text), reference_number=reference_number, authors=authors, year=year,
            title=title, publisher=publisher, journal=None, volume_issue=volume_match.group(1) if volume_match else None,
            page_range=_digits(page_match.group(1)) if page_match else None,
            doi=doi_match.group(1) if doi_match else None, url=url_match.group(0) if url_match else None,
            confidence=min(confidence, .95),
        ))
    result = []
    for entry in entries:
        item = asdict(entry)
        item['authors'] = list(entry.authors)
        result.append(item)
    return result


def link_citations(citations: list[dict[str, Any]], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Link bibliography syntax only; ambiguity is preserved rather than guessed."""
    links = []
    for citation in citations:
        candidates: list[dict[str, Any]] = []
        if citation.get('reference_numbers'):
            numbers = set(citation['reference_numbers'])
            candidates = [entry for entry in entries if entry.get('reference_number') in numbers]
        elif citation.get('authors') and citation.get('year'):
            citation_authors = set(citation['authors'])
            candidates = [entry for entry in entries if entry.get('year') == citation['year'] and citation_authors.intersection(entry.get('authors', []))]
        if len(candidates) == 1:
            status = 'LINKED'
        elif len(candidates) > 1:
            status = 'AMBIGUOUS'
        elif entries:
            status = 'UNRESOLVED'
        else:
            status = 'NO_REFERENCE_FOUND'
        links.append({
            'citation_start': citation['start'], 'citation_end': citation['end'],
            'citation_text': citation['text'], 'status': status,
            'candidate_entry_ids': [item['entry_id'] for item in candidates],
            'linked_entry': candidates[0] if status == 'LINKED' else None,
            'linkage_is_not_source_verification': True,
            'review_required': status != 'LINKED',
        })
    return links
