# -*- coding: utf-8 -*-
"""
وحدة استخراج نصوص المستندات مع الحفاظ التام على أرقام الصفحات (Page-Level Document Extractor):
- استخراج صفحة-بصفحة من ملفات PDF مع حفظ رقم الصفحة الأصلي بدقة.
- استخراج فقرات مستندات Word (.docx) و (.txt) مع وسم رقم الصفحة بـ None (غير متاح).
- دعم معالجة الحروف المعكوسة (Bidi) وتنظيف شوائب خطوط PDF العربية.
- تفعيل OCR للصفحات المصمتة ولطبقات النص العربية ذات الترميز التالف.
"""

import os
import re
import json
import time
import uuid
import hashlib
import logging
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Optional

import config
from .ocr_engine import check_ocr_availability, ocr_page_pixmap

logger = logging.getLogger(__name__)

_PDF_EXTRACTION_CACHE_SCHEMA = 'pdf-pages-v1'

# الكلمات المعكوسة الشائعة لاكتشاف مشاكل الـ Bidi
_REVERSED_ARABIC = re.compile(r'\b(ة[ا-ي]{2,}|[ا-ي]{2,}لا|[ا-ي]{2,}ةي|هيلع|ءاكذ|ميلعت)\b')
_ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
_LATIN_CHAR_RE = re.compile(r'[a-zA-Z]')
_LEGACY_PDF_GLYPH_RE = re.compile(r'[\u0080-\u009F\u00E5\u00C5]')


def pdf_text_needs_ocr(text: str, min_words: int = 20) -> tuple[bool, str]:
    """Detect empty/scanned pages and corrupt legacy Arabic PDF text layers."""
    if not text or not text.strip():
        return True, 'empty'

    arabic_chars = len(_ARABIC_CHAR_RE.findall(text))
    replacement_chars = text.count('\uFFFD')
    control_chars = sum(
        1 for char in text
        if unicodedata.category(char) in ('Cc', 'Co', 'Cs', 'Cn') and char not in '\n\r\t'
    )
    legacy_glyphs = len(_LEGACY_PDF_GLYPH_RE.findall(text))
    # Control/replacement characters are a broken text layer regardless of the
    # document language.  The previous Arabic-only guard allowed English slide
    # decks encoded as control glyphs to bypass OCR and become punctuation junk.
    if replacement_chars or control_chars:
        return True, 'corrupt_text_layer'
    if arabic_chars >= 20 and legacy_glyphs:
        return True, 'corrupt_text_layer'

    words = text.split()
    if len(words) < min_words:
        return True, 'sparse'

    return False, ''


_FRAGMENTED_ARABIC_SEQ = re.compile(r'(?:^|\s)(?:[\u0600-\u06FF]\s+){2,}[\u0600-\u06FF](?:\s|$)')


def count_meaningful_words(text: str) -> tuple[int, int, int, int]:
    """
    Count meaningful Arabic and English/Latin words and inspect Arabic tokens.
    Returns:
        (meaningful_words, total_tokens, single_arabic_tokens, total_arabic_tokens)
    """
    tokens = text.split()
    if not tokens:
        return 0, 0, 0, 0

    meaningful = 0
    single_ar = 0
    total_ar = 0

    for tok in tokens:
        stripped = tok.strip(' \t\n\r()[]{}<>.,;:!?\'"«»ـ-—/\\')
        if not stripped:
            continue
        ar_letters = sum(
            1 for c in stripped
            if _ARABIC_CHAR_RE.match(c) and unicodedata.category(c).startswith('L') and c != '\u0640'
        )
        lat_letters = sum(
            1 for c in stripped
            if _LATIN_CHAR_RE.match(c) and unicodedata.category(c).startswith('L')
        )

        if ar_letters >= 2 and ar_letters >= len(stripped) * 0.6:
            meaningful += 1
            total_ar += 1
        elif ar_letters == 1 and len(stripped) == 1:
            single_ar += 1
            total_ar += 1
        elif lat_letters >= 2 and lat_letters >= len(stripped) * 0.6:
            meaningful += 1

    return meaningful, len(tokens), single_ar, total_ar


def pdf_text_quality_score(text: str) -> float:
    """
    Conservative text-quality scorer:
    - Detect replacement/control/private/unassigned/legacy glyphs.
    - Measure meaningful Arabic/English word coverage.
    - Detect fragmented Arabic letters (e.g. 'ا ل د ر ا س ة').
    - Reward dense, continuous Arabic/English text.
    Returns float in range [0.0, 1.0].
    """
    if not text or not text.strip():
        return 0.0

    bad_glyphs = 0
    non_space_chars = 0
    arabic_chars = 0
    latin_chars = 0
    digits = 0

    for c in text:
        if c.isspace():
            continue
        non_space_chars += 1
        cat = unicodedata.category(c)
        if (cat in ('Cc', 'Co', 'Cs', 'Cn') and c not in '\n\r\t') or c == '\uFFFD' or _LEGACY_PDF_GLYPH_RE.match(c):
            bad_glyphs += 1
        elif _ARABIC_CHAR_RE.match(c) and cat.startswith('L') and c != '\u0640':
            arabic_chars += 1
        elif _LATIN_CHAR_RE.match(c) and cat.startswith('L'):
            latin_chars += 1
        elif c.isdigit():
            digits += 1

    if non_space_chars == 0:
        return 0.0

    if bad_glyphs > 0:
        bad_ratio = bad_glyphs / non_space_chars
        if bad_glyphs >= 3 or bad_ratio > 0.01:
            return 0.0
        glyph_penalty = bad_glyphs * 0.30
    else:
        glyph_penalty = 0.0

    meaningful_words, total_tokens, single_ar, total_ar = count_meaningful_words(text)
    if total_tokens == 0:
        return 0.0

    frag_seqs = _FRAGMENTED_ARABIC_SEQ.findall(text)
    frag_seq_chars = sum(len(s.split()) for s in frag_seqs)

    frag_penalty = 0.0
    if total_ar > 0:
        frag_ratio = single_ar / total_ar
        if frag_ratio > 0.12:
            frag_penalty += (frag_ratio - 0.12) * 1.5
    if frag_seq_chars >= 3:
        frag_penalty += min(0.70, frag_seq_chars * 0.10)

    meaningful_ratio = meaningful_words / total_tokens
    letter_density = (arabic_chars + latin_chars + digits) / non_space_chars

    base_score = 0.65 * meaningful_ratio + 0.35 * letter_density
    if total_tokens < 10:
        base_score *= (total_tokens / 10.0)

    final_score = max(0.0, min(1.0, base_score - glyph_penalty - frag_penalty))
    return round(final_score, 4)


def native_pdf_text_is_sufficient(
    text: str,
    min_words: Optional[int] = None,
    min_quality: Optional[float] = None,
) -> bool:
    """
    Determine whether a native PDF text layer is sufficiently dense and clean
    to safely skip expensive full-page raster OCR.
    Requirements:
    1. pdf_text_needs_ocr(text) must be False.
    2. Meaningful words >= config.PDF_NATIVE_TEXT_MIN_WORDS.
    3. pdf_text_quality_score(text) >= config.PDF_NATIVE_TEXT_MIN_QUALITY.
    """
    if not text or not text.strip():
        return False

    needs_ocr, _ = pdf_text_needs_ocr(text)
    if needs_ocr:
        return False

    if min_words is None:
        min_words = int(getattr(config, 'PDF_NATIVE_TEXT_MIN_WORDS', 30))
    if min_quality is None:
        min_quality = float(getattr(config, 'PDF_NATIVE_TEXT_MIN_QUALITY', 0.82))

    meaningful_words, _, _, _ = count_meaningful_words(text)
    if meaningful_words < min_words:
        return False

    quality = pdf_text_quality_score(text)
    if quality < min_quality:
        return False

    return True



def clean_arabic_pdf_glyphs(text: str) -> str:
    """
    تنظيف الشوائب الناتجة عن فك ترميز خطوط PDF العربية:
    - إزالة المحارف الصفرية المعطوبة.
    - تصحيح الشوائب الشهيرة مثل (امل / املم -> ال).
    - تصحيح بعض الكلمات المعكوسة شائعة الحدوث في عناوين الخطوط القديمة.
    """
    if not text:
        return ''

    text = unicodedata.normalize('NFKC', text)
    # إزالة الرموز والمحارف التحكمية غير المقروءة
    text = re.sub(r'[\uFFFD\u0000-\u0008\u000B\u000C\u000E-\u001F\u25C6\u25C7\u25A0\u25A1]', ' ', text)
    text = re.sub(r'[\u200E\u200F\u202A-\u202E\u2066-\u2069]', '', text)
    text = text.replace('\u0640', '')  # إزالة الكشيدة

    # تصحيح تراكيب ال التعريف الشائعة في الخطوط المعطوبة
    text = re.sub(r'\bاملم([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bامل([ا-ي]{2,})', r'الم\1', text)
    text = re.sub(r'\bيف\b', 'في', text)
    text = re.sub(r'\bعل[»|م]\b', 'على', text)
    text = re.sub(r'\bإل[»|م]\b', 'إلى', text)

    return text


def unreverse_arabic_text(text: str) -> str:
    """
    كشف وتصحيح الكلمات العربية المعكوسة من ملفات الـ PDF القديمة مع تجنب المساس بالنصوص الإنجليزية والفرنسية.
    """
    if not text:
        return ''

    lines = text.split('\n')
    out_lines = []

    for line in lines:
        if _LATIN_CHAR_RE.search(line):
            out_lines.append(line)
            continue

        words = line.split()
        if not words:
            out_lines.append(line)
            continue

        arabic_words = [w for w in words if _ARABIC_CHAR_RE.search(w)]
        if len(arabic_words) < 3:
            out_lines.append(line)
            continue

        rev_count = sum(1 for w in arabic_words if w.startswith('ة') or w.endswith('لا') or w.startswith('ات'))
        if (rev_count / len(arabic_words)) >= 0.55:
            # ترتيب الكلمات والحروف معكوس
            fixed = []
            for w in reversed(words):
                fixed.append(w[::-1])
            out_lines.append(' '.join(fixed))
        else:
            out_lines.append(line)

    return '\n'.join(out_lines)


def extract_document_pages(
    file_path: str,
    enable_ocr: bool = True,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict]:
    """
    استخراج محتوى المستند صفحة-بصفحة.
    يرجع قائمة بالقواميس:
    [
        {'page_number': 1, 'text': '...', 'is_ocr': False},
        ...
    ]
    في ملفات Word و TXT، تكون قيمة 'page_number': None
    """
    ext = os.path.splitext(file_path)[1].lower()
    pages: list[dict] = []

    if ext == '.pdf':
        pages = _extract_pdf_pages_cached(
            file_path,
            enable_ocr=enable_ocr,
            progress_callback=progress_callback,
        )
    elif ext in ('.docx', '.doc'):
        # DOCX has no stable page model of its own. When a local office engine
        # can render it, extract from the same PDF preview used by the report
        # viewer so new evidence keeps real page numbers and coordinates.
        pages = []
        if ext == '.docx':
            try:
                from app.services.document_preview_service import ensure_pdf_preview
                preview_path = ensure_pdf_preview(file_path)
                pages = _extract_pages_from_pdf(
                    str(preview_path),
                    enable_ocr=False,
                    progress_callback=progress_callback,
                )
            except Exception as preview_error:
                logger.warning(
                    "تعذر إنشاء معاينة PDF لملف Word؛ سيتم الاستخراج النصي دون أرقام صفحات: %s",
                    preview_error,
                )
        if not pages:
            pages = _extract_pages_from_docx(file_path)
    elif ext == '.txt':
        pages = _extract_pages_from_txt(file_path)
    else:
        logger.warning(f"صيغة ملف غير مدعومة للاستخراج: {ext}")

    return pages


def _stream_file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_extraction_cache_path(path: str, enable_ocr: bool) -> Path | None:
    """Build a content-addressed cache key that changes with OCR behaviour."""
    if not getattr(config, 'PDF_EXTRACTION_CACHE_ENABLED', True):
        return None
    source = Path(path)
    if not source.is_file():
        return None
    identity = {
        'schema': _PDF_EXTRACTION_CACHE_SCHEMA,
        'sha256': _stream_file_sha256(str(source)),
        'enable_ocr': bool(enable_ocr),
        'dpi': int(getattr(config, 'PDF_OCR_DPI', 220)),
        'smart_ocr': bool(getattr(config, 'SMART_PDF_OCR_ENABLED', True)),
        'native_min_words': int(getattr(config, 'PDF_NATIVE_TEXT_MIN_WORDS', 30)),
        'native_min_quality': float(getattr(config, 'PDF_NATIVE_TEXT_MIN_QUALITY', 0.82)),
        'languages': 'ara+eng',
    }
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    root = Path(
        getattr(
            config,
            'PDF_EXTRACTION_CACHE_DIR',
            Path(config.STORAGE_ROOT) / 'pdf_extraction_cache',
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root / f'{key}.json'


def _read_pdf_extraction_cache(cache_path: Path | None) -> list[dict] | None:
    if cache_path is None or not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
        if payload.get('schema') != _PDF_EXTRACTION_CACHE_SCHEMA:
            return None
        pages = payload.get('pages')
        if not isinstance(pages, list) or not pages:
            return None
        for page in pages:
            if not isinstance(page, dict) or 'page_number' not in page or not isinstance(page.get('text'), str):
                return None
        os.utime(cache_path, None)
        return pages
    except Exception as exc:
        logger.debug("تعذر قراءة كاش استخراج PDF %s: %s", cache_path, exc)
        return None


def _prune_pdf_extraction_cache(root: Path, protected_path: Path | None = None) -> None:
    max_bytes = int(getattr(config, 'PDF_EXTRACTION_CACHE_MAX_MB', 1024)) * 1024 * 1024
    try:
        entries = [p for p in root.glob('*.json') if p.is_file()]
        total = sum(p.stat().st_size for p in entries)
        if total <= max_bytes:
            return
        for entry in sorted(entries, key=lambda p: p.stat().st_mtime):
            if protected_path is not None and entry == protected_path:
                continue
            size = entry.stat().st_size
            entry.unlink(missing_ok=True)
            total -= size
            if total <= max_bytes:
                break
    except Exception as exc:
        logger.debug("تعذر تقليم كاش استخراج PDF: %s", exc)


def _write_pdf_extraction_cache(cache_path: Path | None, pages: list[dict]) -> None:
    if cache_path is None or not pages:
        return
    temp_path = cache_path.with_name(f'.{cache_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    try:
        temp_path.write_text(
            json.dumps(
                {'schema': _PDF_EXTRACTION_CACHE_SCHEMA, 'pages': pages},
                ensure_ascii=False,
                separators=(',', ':'),
            ),
            encoding='utf-8',
        )
        os.replace(temp_path, cache_path)
        _prune_pdf_extraction_cache(cache_path.parent, protected_path=cache_path)
    except Exception as exc:
        logger.debug("تعذر حفظ كاش استخراج PDF %s: %s", cache_path, exc)
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _extract_pdf_pages_cached(
    path: str,
    enable_ocr: bool = True,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict]:
    started = time.perf_counter()
    cache_path = _pdf_extraction_cache_path(path, enable_ocr)
    cached_pages = _read_pdf_extraction_cache(cache_path)
    if cached_pages is not None:
        total = len(cached_pages)
        if progress_callback:
            _notify_pdf_progress(progress_callback, total, total, total)
        logger.info(
            "تم استخدام كاش استخراج PDF الكامل: %s صفحة خلال %.2f ثانية.",
            total,
            time.perf_counter() - started,
        )
        return cached_pages

    pages = _extract_pages_from_pdf(
        path,
        enable_ocr=enable_ocr,
        progress_callback=progress_callback,
    )
    _write_pdf_extraction_cache(cache_path, pages)
    logger.info(
        "اكتمل استخراج PDF وحفظ الكاش: %s صفحة خلال %.2f ثانية.",
        len(pages),
        time.perf_counter() - started,
    )
    return pages


def _notify_pdf_progress(callback, completed: int, total: int, page_number: int) -> None:
    if not callback:
        return
    try:
        callback(completed, total, page_number)
    except Exception as exc:
        logger.debug("تعذر إرسال تقدم استخراج PDF: %s", exc)


def _clean_pdf_page_result(text: str, logical_direction: bool) -> str:
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', text)
    if not logical_direction:
        text = unreverse_arabic_text(text)
    return clean_arabic_pdf_glyphs(text).strip()


def _normalized_ocr_line(text: str) -> str:
    """Normalize a native/OCR line for conservative duplicate detection."""
    return re.sub(r'[^0-9a-z\u0600-\u06ff]+', '', (text or '').casefold())


def merge_native_and_image_ocr_text(native_text: str, ocr_text: str) -> tuple[str, bool]:
    """Append only useful OCR lines that are not already in the PDF text layer."""
    native_clean = _clean_pdf_page_result(native_text, False)
    ocr_clean = _clean_pdf_page_result(ocr_text, True)
    if not ocr_clean:
        return native_clean, False
    if not native_clean:
        return ocr_clean, True

    native_lines = [
        _normalized_ocr_line(line)
        for line in native_clean.splitlines()
        if _normalized_ocr_line(line)
    ]
    native_compact = _normalized_ocr_line(native_clean)
    additions = []
    seen = set()
    for raw_line in ocr_clean.splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip()
        normalized = _normalized_ocr_line(line)
        # Ignore isolated OCR specks while retaining short names/logos such as
        # "INSTANT Software" and their Arabic equivalents.
        if len(normalized) < 5 or normalized in seen:
            continue
        seen.add(normalized)
        if normalized in native_compact:
            continue
        if any(SequenceMatcher(None, normalized, existing).ratio() >= 0.90 for existing in native_lines):
            continue
        additions.append(line)

    if not additions:
        return native_clean, False
    return f"{native_clean}\n\n" + '\n'.join(additions), True


def pdf_page_has_large_image(page, min_area_ratio: float = 0.08) -> bool:
    """Return True when a raster image occupies a meaningful part of a PDF page."""
    try:
        page_area = float(page.rect.get_area())
        if page_area <= 0:
            return False
        seen_xrefs = set()
        for image in page.get_images(full=True):
            xref = int(image[0])
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            for rect in page.get_image_rects(xref):
                visible = rect & page.rect
                if not visible.is_empty and (float(visible.get_area()) / page_area) >= min_area_ratio:
                    return True
    except Exception as exc:
        logger.debug("تعذر قياس الصور المضمنة في صفحة PDF: %s", exc)
    return False


def alternative_pdf_text_is_usable(primary_text: str, alternative_text: str) -> bool:
    """Accept a clean alternate text layer only when it preserves enough Arabic."""
    if not alternative_text or len(alternative_text.split()) < 20:
        return False
    alternative_needs_ocr, _ = pdf_text_needs_ocr(alternative_text)
    if alternative_needs_ocr:
        return False

    primary_arabic = len(_ARABIC_CHAR_RE.findall(primary_text or ''))
    alternative_arabic = len(_ARABIC_CHAR_RE.findall(alternative_text))
    if primary_arabic < 40:
        return alternative_arabic >= 20
    return (alternative_arabic / primary_arabic) >= 0.70


def _ocr_pdf_pixmap(
    pixmap,
    original_text: str,
    original_word_count: int,
    languages: str,
    merge_with_original: bool = False,
) -> tuple[str, bool]:
    """OCR worker for one already-rendered page, returning safe fallback text."""
    try:
        ocr_text = ocr_page_pixmap(pixmap, languages=languages)
        minimum_words = 2 if merge_with_original else (
            4 if original_word_count < 20 else max(8, int(original_word_count * 0.25))
        )
        if ocr_text and len(ocr_text.split()) >= minimum_words:
            if merge_with_original:
                return merge_native_and_image_ocr_text(original_text, ocr_text)
            return _clean_pdf_page_result(ocr_text, True), True
    except Exception as exc:
        logger.debug("فشل OCR لإحدى صفحات PDF: %s", exc)
    return _clean_pdf_page_result(original_text, False), False


def _extract_pages_from_pdf(
    path: str,
    enable_ocr: bool = True,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> list[dict]:
    """استخراج PDF بصفحات OCR متوازية ومحدودة الذاكرة مع حفظ الترتيب."""
    ocr_status = check_ocr_availability() if enable_ocr else {'available': False}

    # المحاولة الأولى: PyMuPDF (fitz)
    try:
        import fitz
        with fitz.open(path) as doc:
            total_pages = len(doc)
            pages: list[Optional[dict]] = [None] * total_pages
            completed = 0
            worker_count = min(
                max(1, int(getattr(config, 'PDF_OCR_WORKERS', 2))),
                max(1, int(getattr(config, 'MAX_CONCURRENT_OCR_JOBS', 2))),
            )
            dpi = int(getattr(config, 'PDF_OCR_DPI', 220))
            if enable_ocr and ocr_status.get('available'):
                logger.info(
                    "تهيئة OCR متكيف: %s عامل/عوامل، دقة %s DPI، كاش الصفحات %s.",
                    worker_count,
                    dpi,
                    'مفعل' if getattr(config, 'OCR_CACHE_ENABLED', True) else 'معطل',
                )
            max_pending = max(2, worker_count * 2)
            pending = {}
            alternate_reader = None
            alternate_reader_failed = False

            def collect(done_futures) -> None:
                nonlocal completed
                for future in done_futures:
                    page_idx, page_num, hybrid_ocr = pending.pop(future)
                    try:
                        page_text, is_ocr = future.result()
                    except Exception as exc:
                        logger.warning("فشل عامل OCR للصفحة %s: %s", page_num, exc)
                        page_text, is_ocr = '', False
                    pages[page_idx] = {
                        'page_number': page_num,
                        'text': page_text,
                        'is_ocr': is_ocr,
                        'extraction_engine': (
                            'pymupdf+tesseract' if is_ocr and hybrid_ocr
                            else ('tesseract' if is_ocr else 'pymupdf')
                        ),
                    }
                    completed += 1
                    _notify_pdf_progress(progress_callback, completed, total_pages, page_num)

            smart_ocr_enabled = getattr(config, 'SMART_PDF_OCR_ENABLED', True)
            ocr_pages_submitted = 0
            smart_ocr_skips = 0

            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='pdf-ocr') as executor:
                for idx, page in enumerate(doc):
                    page_num = idx + 1
                    text = page.get_text('text') or ''
                    words = text.split()
                    needs_ocr, ocr_reason = pdf_text_needs_ocr(text)
                    has_large_image = pdf_page_has_large_image(page)
                    from_alternate = False

                    # A second PDF parser can often recover a clean logical Arabic
                    # text layer even when PyMuPDF exposes legacy control glyphs.
                    # This avoids expensive OCR on most born-digital pages.
                    if needs_ocr and not alternate_reader_failed:
                        if alternate_reader is None:
                            try:
                                from pypdf import PdfReader
                                alternate_reader = PdfReader(path)
                            except Exception as exc:
                                logger.warning("تعذر فتح طبقة النص البديلة: %s", exc)
                                alternate_reader_failed = True
                        try:
                            if alternate_reader is None:
                                raise RuntimeError('alternate PDF reader is unavailable')
                            alternate_text = alternate_reader.pages[idx].extract_text() or ''
                            if alternative_pdf_text_is_usable(text, alternate_text):
                                text = alternate_text
                                words = text.split()
                                needs_ocr = False
                                from_alternate = True
                        except Exception as exc:
                            logger.debug("تعذر استخراج طبقة النص البديلة للصفحة %s: %s", page_num, exc)

                    should_ocr = False
                    hybrid_ocr = False

                    if needs_ocr:
                        should_ocr = True
                        hybrid_ocr = False
                    elif has_large_image:
                        if smart_ocr_enabled and native_pdf_text_is_sufficient(text):
                            should_ocr = False
                            smart_ocr_skips += 1
                            logger.info(
                                "الصفحة %s: تم تخطي OCR الذكي بنجاح لوجود طبقة نصية عربية أصلية ونظيفة وكثيفة (%s كلمة).",
                                page_num,
                                len(words),
                            )
                        else:
                            should_ocr = True
                            hybrid_ocr = True
                            if not ocr_reason:
                                ocr_reason = 'image_insufficient_text' if smart_ocr_enabled else 'embedded_image'

                    can_ocr = (
                        should_ocr
                        and enable_ocr
                        and ocr_status.get('available')
                        and ocr_status.get('has_arabic')
                    )

                    if can_ocr:
                        ocr_pages_submitted += 1
                        logger.info(
                            "الصفحة %s تحتاج OCR (%s، %s كلمة) بدقة %s DPI...",
                            page_num, ocr_reason or 'embedded_image', len(words), dpi,
                        )
                        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
                        # Always load both bundled models: text inside an image
                        # can use a different language from the searchable layer.
                        languages = 'ara+eng'
                        future = executor.submit(
                            _ocr_pdf_pixmap,
                            pix,
                            text,
                            len(words),
                            languages,
                            hybrid_ocr,
                        )
                        pending[future] = (idx, page_num, hybrid_ocr)

                        if len(pending) >= max_pending:
                            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                            collect(done)
                    else:
                        pages[idx] = {
                            'page_number': page_num,
                            'text': _clean_pdf_page_result(text, from_alternate),
                            'is_ocr': False,
                            'extraction_engine': 'pypdf' if from_alternate else 'pymupdf',
                        }
                        completed += 1
                        _notify_pdf_progress(progress_callback, completed, total_pages, page_num)

                while pending:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    collect(done)

            logger.info(
                "اكتمال استخراج صفحات PDF: إجمالي الصفحات %s، تم إرسال %s صفحة للـ OCR، وتخطي %s صفحة بـ Smart OCR.",
                total_pages,
                ocr_pages_submitted,
                smart_ocr_skips,
            )

            return [page for page in pages if page is not None]
    except Exception as e:
        logger.warning(f"تعذر استخراج PDF بـ PyMuPDF: {e}. جاري استخدام pdfplumber...")

    # المحاولة البديلة: pdfplumber
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for idx, p in enumerate(pdf.pages):
                page_num = idx + 1
                t = p.extract_text() or ''
                if t:
                    t = unicodedata.normalize('NFKC', t)
                    t = unreverse_arabic_text(t)
                    t = clean_arabic_pdf_glyphs(t)
                pages.append({
                    'page_number': page_num,
                    'text': t.strip(),
                    'is_ocr': False
                })
                _notify_pdf_progress(progress_callback, idx + 1, total_pages, page_num)
        return pages
    except Exception as e2:
        logger.error(f"فشل استخراج ملف PDF بالكامل: {e2}")
        return []


def _extract_pages_from_docx(path: str) -> list[dict]:
    """استخراج نصوص Word مع التوثيق الصريح بأن رقم الصفحة غير متاح."""
    try:
        import docx
        doc = docx.Document(path)
        full_paragraphs = []
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                full_paragraphs.append(clean_arabic_pdf_glyphs(p.text.strip()))

        # استخراج نصوص الجداول أيضاً
        for tbl in doc.tables:
            for row in tbl.rows:
                row_txt = [c.text.strip() for c in row.cells if c.text.strip()]
                if row_txt:
                    full_paragraphs.append(' | '.join(row_txt))

        joined = '\n\n'.join(full_paragraphs)
        return [{
            'page_number': None,  # غير متاح لملفات Word
            'text': joined,
            'is_ocr': False
        }]
    except Exception as e:
        logger.error(f"فشل استخراج ملف DOCX: {e}")
        return []


def _extract_pages_from_txt(path: str) -> list[dict]:
    """استخراج النصوص العادية بترميز UTF-8 القياسي أو Windows-1256 العربي."""
    try:
        for enc in ['utf-8', 'utf-8-sig', 'windows-1256']:
            try:
                with open(path, 'r', encoding=enc) as f:
                    text = f.read()
                return [{
                    'page_number': None,
                    'text': clean_arabic_pdf_glyphs(text),
                    'is_ocr': False
                }]
            except UnicodeDecodeError:
                continue
    except Exception as e:
        logger.error(f"فشل استخراج ملف TXT: {e}")
    return []


def extract_text(file_path: str) -> str:
    """
    دالة للتوافق العكسي الكامل مع المستدعين القدامى: ترجع النص الكامل للمستند كسلسلة نصية واحدة.
    """
    pages = extract_document_pages(file_path, enable_ocr=False)
    return '\n\n'.join(p['text'] for p in pages if p['text'])
