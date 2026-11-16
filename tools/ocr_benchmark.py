# -*- coding: utf-8 -*-
"""Offline manifest-driven Arabic OCR evaluation; real labels are supplied by users."""
from __future__ import annotations
import argparse, json, re, time, unicodedata
from pathlib import Path
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text).strip()


def levenshtein(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, value in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (value != other)))
        previous = current
    return previous[-1]


def score(reference: str, actual: str) -> dict:
    ref, out = normalize(reference), normalize(actual)
    cer_den, wer_den = len(ref), len(ref.split())
    return {
        'cer': levenshtein(list(ref), list(out)) / cer_den if cer_den else None,
        'wer': levenshtein(ref.split(), out.split()) / wer_den if wer_den else None,
        'reference_characters': cer_den, 'reference_words': wer_den,
        'completeness': SequenceMatcher(None, ref, out).ratio() if ref else None,
    }


def run(manifest: Path) -> dict:
    from plagiarism_detector.extraction.ocr_engine import ocr_page_pixmap
    from PIL import Image
    import psutil
    pages = json.loads(manifest.read_text(encoding='utf-8'))['pages']
    results=[]; process=psutil.Process()
    for page in pages:
        start=time.perf_counter(); before=process.memory_info().rss
        with Image.open(manifest.parent / page['image']) as image:
            output=ocr_page_pixmap(image, languages=page.get('languages','ara+eng'))
        item={'id':page['id'], **score(page['transcription'],output),
              'seconds':round(time.perf_counter()-start,4), 'rss_delta_bytes':process.memory_info().rss-before,
              'page_attribution_correct': bool(page.get('page_number'))}
        results.append(item)
    return {'synthetic': all(p.get('synthetic',False) for p in pages), 'normalization':'NFKC + combining-mark removal + whitespace collapse','pages':results}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('manifest', type=Path); parser.add_argument('--output', type=Path)
    args=parser.parse_args(); data=run(args.manifest); encoded=json.dumps(data,ensure_ascii=False,indent=2)
    if args.output: args.output.write_text(encoded,encoding='utf-8')
    else: print(encoded)
