"""Original extracted-text spans for offline AI research."""

from itertools import chain
import re


_LINE_END = r'(?:\r\n|\r(?!\n)|(?<!\r)\n)'
_PARAGRAPH_BREAK = re.compile(rf'{_LINE_END}(?:[^\S\r\n]*{_LINE_END})+')
# Bound the untruncated tokenizer pass before the model's token limit is applied.
MAX_PARAGRAPH_CHARACTERS = 32_768


def iter_paragraphs(raw_text, pages=None):
    """Yield blank-line-delimited spans without changing their Unicode text.

    Document offsets refer to nonempty extracted page texts joined with two
    LF characters, or to raw_text when pages are absent. Page numbers may be
    repeated across files. page_index identifies the supplied page record.
    """
    paragraph_id = 0
    document_offset = 0
    for page_index, page in enumerate(pages or [{'text': raw_text}]):
        text = page['text']
        if not text:
            continue
        start = 0
        spans = ((match.start(), match.end()) for match in _PARAGRAPH_BREAK.finditer(text))
        for end, next_start in chain(spans, [(len(text), len(text))]):
            original = text[start:end]
            if original.strip():
                paragraph_id += 1
                yield {
                    'paragraph_id': paragraph_id,
                    'page_index': page_index,
                    'page_number': page.get('page_number'),
                    'file_index': page.get('file_index'),
                    'source_file': page.get('source_file'),
                    'is_ocr': page.get('is_ocr'),
                    'text': original,
                    'start_offset': start,
                    'end_offset': end,
                    'document_start_offset': document_offset + start,
                    'document_end_offset': document_offset + end,
                }
            start = next_start
        document_offset += len(text) + 2


def paragraph_evidence(paragraph):
    """Whitelist source metadata so reference labels cannot enter predictions."""
    return {key: paragraph.get(key) for key in (
        'paragraph_id', 'page_index', 'page_number', 'file_index', 'source_file',
        'is_ocr', 'text', 'start_offset', 'end_offset', 'document_start_offset',
        'document_end_offset',
    )}
