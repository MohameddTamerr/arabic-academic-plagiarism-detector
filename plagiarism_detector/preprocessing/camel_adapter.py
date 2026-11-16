# -*- coding: utf-8 -*-
"""
CAMeL Tools Integration Adapter for Arabic Academic Plagiarism Detection.

Provides:
1. Unicode normalization (NFC via CAMeL normalize_unicode).
2. Alef and Alef Maksura normalization via CAMeL normalize_alef_ar / normalize_alef_maksura_ar.
3. Diacritics removal via CAMeL dediac_ar.
4. Teh Marbuta normalization via CAMeL normalize_teh_marbuta_ar.
5. Offset-preserving word tokenization (OriginalToken) ensuring 100% faithful
   Unicode character offsets for visual PDF highlighting.
6. Academic-safe text normalization combining CAMeL primitives with essential
   PDF extraction hygiene (Tatweel and zero-width character stripping).
7. Optional morphological analysis and context-aware lemmatization with graceful
   offline fallback when heavy external databases are absent.
"""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Ensure vendor directory is in sys.path
import os
_VENDOR_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'vendor'))
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

# Probe CAMeL Tools availability
_CAMEL_AVAILABLE = False
try:
    from camel_tools.tokenizers.word import simple_word_tokenize
    from camel_tools.utils.dediac import dediac_ar
    from camel_tools.utils.normalize import (
        normalize_alef_ar,
        normalize_alef_maksura_ar,
        normalize_teh_marbuta_ar,
        normalize_unicode,
    )
    _CAMEL_AVAILABLE = True
except ImportError:
    pass

# Characters requiring removal in academic PDF extraction
_TATWEEL_CHAR = '\u0640'
_ZERO_WIDTH_RE = re.compile(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]')
_NON_WORD_RE = re.compile(r'[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\w\s]')

# Built-in fallback transformations
_FALLBACK_DIACRITICS_RE = re.compile(
    r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]'
)
_FALLBACK_LIGHT_TRANS = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي',
})
_FALLBACK_AGGRESSIVE_TRANS = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي',
    'ة': 'ه', 'ء': 'ا', 'ؤ': 'و', 'ئ': 'ي',
})


def is_camel_available() -> bool:
    """Return True if CAMeL Tools is installed and importable."""
    return _CAMEL_AVAILABLE


def camel_normalize_unicode(text: str, compatibility: bool = False) -> str:
    """Normalize Arabic Unicode representation using CAMeL Tools (or unicodedata fallback)."""
    if not text:
        return ''
    if _CAMEL_AVAILABLE:
        return normalize_unicode(text, compatibility=compatibility)
    return unicodedata.normalize('NFKD' if compatibility else 'NFC', text)


def camel_normalize_alef(text: str) -> str:
    """Normalize variants of Alef (أ, إ, آ, ٱ -> ا) using CAMeL Tools."""
    if not text:
        return ''
    if _CAMEL_AVAILABLE:
        return normalize_alef_ar(text)
    return text.translate(_FALLBACK_LIGHT_TRANS)


def camel_normalize_alef_maksura(text: str) -> str:
    """Normalize Alef Maksura (ى -> ي) using CAMeL Tools."""
    if not text:
        return ''
    if _CAMEL_AVAILABLE:
        return normalize_alef_maksura_ar(text)
    return text.replace('ى', 'ي')


def camel_normalize_teh_marbuta(text: str) -> str:
    """Normalize Teh Marbuta (ة -> ه) using CAMeL Tools."""
    if not text:
        return ''
    if _CAMEL_AVAILABLE:
        return normalize_teh_marbuta_ar(text)
    return text.replace('ة', 'ه')


def camel_dediac(text: str) -> str:
    """Remove Arabic diacritical marks using CAMeL Tools."""
    if not text:
        return ''
    if _CAMEL_AVAILABLE:
        return dediac_ar(text)
    return _FALLBACK_DIACRITICS_RE.sub('', text)


def camel_normalize_light(text: str) -> str:
    """
    CAMeL-based light normalization for TF-IDF, retrieval, and semantic similarity.
    - Applies CAMeL Unicode normalization (NFC).
    - Strips PDF tatweel and zero-width artifacts.
    - Strips diacritics via CAMeL dediac_ar.
    - Unifies Alef variants and Alef Maksura via CAMeL Tools.
    - Preserves Teh Marbuta (ة) and separate Hamzas to maintain semantic precision.
    """
    if not text:
        return ''
    # 1. Unicode normalization
    text = camel_normalize_unicode(text, compatibility=False)
    # 2. PDF extraction hygiene
    text = _ZERO_WIDTH_RE.sub('', text)
    text = text.replace(_TATWEEL_CHAR, '')
    # 3. Diacritics removal via CAMeL
    text = camel_dediac(text)
    # 4. Alef and Alef Maksura normalization via CAMeL
    text = camel_normalize_alef(text)
    text = camel_normalize_alef_maksura(text)
    # 5. Non-word characters and spacing
    text = _NON_WORD_RE.sub(' ', text)
    return ' '.join(text.split()).strip()


def camel_normalize_aggressive(text: str) -> str:
    """
    CAMeL-based aggressive normalization for exact/shingle matching.
    - Includes all camel_normalize_light transformations.
    - Unifies Teh Marbuta (ة -> ه) via CAMeL normalize_teh_marbuta_ar.
    - Unifies Hamza variants (ء -> ا, ؤ -> و, ئ -> ي).
    """
    if not text:
        return ''
    text = camel_normalize_unicode(text, compatibility=False)
    text = _ZERO_WIDTH_RE.sub('', text)
    text = text.replace(_TATWEEL_CHAR, '')
    text = camel_dediac(text)
    text = camel_normalize_alef(text)
    text = camel_normalize_alef_maksura(text)
    text = camel_normalize_teh_marbuta(text)
    # Hamza variants
    text = text.replace('ء', 'ا').replace('ؤ', 'و').replace('ئ', 'ي')
    text = _NON_WORD_RE.sub(' ', text)
    return ' '.join(text.split()).strip()


@dataclass(frozen=True)
class CamelToken:
    """Represents a token with original text, normalized text, and exact character offsets."""
    original: str
    normalized: str
    start: int
    end: int
    index: int


def camel_tokenize_words(text: str) -> List[str]:
    """Tokenize Arabic text into words using CAMeL simple_word_tokenize."""
    if not text:
        return []
    if _CAMEL_AVAILABLE:
        return simple_word_tokenize(text)
    return re.findall(r"[^\s،؛؟!.,:;()\[\]{}«»\"'`]+", text)


def camel_tokenize_with_offsets(
    text: str,
    normalize_fn: Optional[Callable[[str], str]] = None,
) -> List[CamelToken]:
    """
    Tokenize text using CAMeL word token boundaries while preserving exact
    character start and end offsets in the original text string for PDF highlighting.
    
    Guarantee: text[token.start:token.end] == token.original
    """
    if not text:
        return []

    norm_fn = normalize_fn if normalize_fn is not None else camel_normalize_aggressive
    raw_tokens = camel_tokenize_words(text)
    tokens: List[CamelToken] = []
    cursor = 0
    token_idx = 0

    for word in raw_tokens:
        if not word:
            continue
        # Find exact occurrence starting from cursor
        pos = text.find(word, cursor)
        if pos == -1:
            # Fallback search if cursor drifted
            pos = text.find(word)
            if pos == -1:
                continue
        start = pos
        end = start + len(word)
        cursor = end

        normalized = norm_fn(word)
        if normalized and any(c.isalnum() for c in normalized):
            tokens.append(CamelToken(
                original=word,
                normalized=normalized,
                start=start,
                end=end,
                index=token_idx,
            ))
            token_idx += 1

    return tokens


# ---------------------------------------------------------------------------
# Morphological Analysis & Lemmatization (Offline & Graceful Fallback)
# ---------------------------------------------------------------------------

_MORPHOLOGY_ANALYZER = None
_MORPHOLOGY_CHECKED = False


def is_morphology_available() -> bool:
    """Return True if CAMeL morphological databases are installed locally."""
    global _MORPHOLOGY_CHECKED, _MORPHOLOGY_ANALYZER
    if not _CAMEL_AVAILABLE:
        return False
    if _MORPHOLOGY_CHECKED:
        return _MORPHOLOGY_ANALYZER is not None
    _MORPHOLOGY_CHECKED = True
    try:
        from camel_tools.morphology.analyzer import Analyzer
        # Attempt to load default database only if local files exist
        _MORPHOLOGY_ANALYZER = Analyzer.pretrained('calima-msa-r13')
        return True
    except Exception as exc:
        logger.debug("CAMeL morphology database not present: %s", exc)
        _MORPHOLOGY_ANALYZER = None
        return False


# Light rule-based academic lemmatizer for offline usage without 1.5GB database
_ARABIC_PREFIXES = ('كال', 'فال', 'بال', 'وال', 'لل', 'ال', 'و', 'ف', 'ب', 'ك', 'ل')
_ARABIC_SUFFIXES = ('هما', 'هما', 'هم', 'هن', 'كما', 'كم', 'كن', 'نا', 'ها', 'ات', 'ين', 'ون', 'ان', 'ي', 'ه', 'ة')


def strip_arabic_proclitics(word: str) -> str:
    """Strip common proclitics (و, ف, بال, فال, كال, لل, ال) while keeping stem length >= 3."""
    if not word or len(word) <= 3:
        return word
    w = word
    if w.startswith('وال') and len(w) > 5:
        w = w[3:]
    elif w.startswith('بال') and len(w) > 5:
        w = w[3:]
    elif w.startswith('فال') and len(w) > 5:
        w = w[3:]
    elif w.startswith('كال') and len(w) > 5:
        w = w[3:]
    elif w.startswith('لل') and len(w) > 4:
        w = w[2:]
    elif w.startswith('ال') and len(w) > 4:
        w = w[2:]
    elif (w.startswith('و') or w.startswith('ف')) and len(w) > 4:
        w = w[1:]
    return w if len(w) >= 3 else word


def light_stem_or_lemmatize(word: str) -> str:
    """
    Safe, conservative morphological lemmatization for Arabic academic words.
    Strips common proclitics and conservative suffixes when root length >= 3.
    """
    if not word or len(word) <= 3:
        return word

    w = strip_arabic_proclitics(word)

    # Strip conservative suffixes if remaining stem has at least 3 letters
    if len(w) > 4:
        for suffix in ('هما', 'تما', 'كما', 'هم', 'هن', 'كم', 'كن', 'نا', 'ها', 'ات', 'ين', 'ون', 'ان'):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[:-len(suffix)]
                break

    return w if len(w) >= 3 else word


def camel_lemmatize_token(word: str) -> str:
    """
    Lemmatize an Arabic word token using CAMeL Analyzer if database is available,
    or conservative offline rule-based lemmatizer.
    """
    if not word:
        return ''
    if is_morphology_available() and _MORPHOLOGY_ANALYZER is not None:
        try:
            analyses = _MORPHOLOGY_ANALYZER.analyze(word)
            if analyses and 'lex' in analyses[0]:
                lemma = analyses[0]['lex'].split('_')[0]
                return camel_dediac(lemma)
        except Exception:
            pass
    return light_stem_or_lemmatize(word)
