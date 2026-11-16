"""Stage 3 bridge between database corpus rows and the disk BM25 index.

The bridge has no database writes.  It validates a checksum-protected local index,
incrementally reconciles source documents by deterministic segment fingerprints,
and returns current scan-local positions expected by the legacy detector.
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import config
from plagiarism_detector.detection.retrieval_index import (
    INDEX_SCHEMA_VERSION,
    LocalDiskRetrievalIndex,
)
from plagiarism_detector.preprocessing.normalizer import normalize_light

logger = logging.getLogger(__name__)

# Keep this explicit rather than importing ``app.versioning``: importing a
# submodule of the Flask package executes its application factory imports and
# would introduce a retrieval/report-builder cycle during standalone tools.
NORMALIZATION_VERSION = "arabic-normalizer-1.0"


def _document_fingerprint(segments: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for segment in sorted(segments, key=lambda value: int(value['seg_id'])):
        digest.update(
            f"{segment['seg_id']}\x1f{segment.get('normalized_text') or normalize_light(segment['raw_text'])}\n".encode('utf-8')
        )
    return digest.hexdigest()


def segment_fingerprint(raw_segments: list[dict[str, Any]]) -> str:
    """Fingerprint exact index inputs, including segment IDs and normalised text."""
    digest = hashlib.sha256()
    for segment in sorted(raw_segments, key=lambda value: (int(value['doc_id']), int(value['seg_id']))):
        digest.update(
            f"{segment['doc_id']}\x1f{segment['seg_id']}\x1f"
            f"{segment.get('normalized_text') or normalize_light(segment['raw_text'])}\n".encode('utf-8')
        )
    return digest.hexdigest()


def _group_by_document(raw_segments: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for segment in raw_segments:
        grouped[int(segment['doc_id'])].append(segment)
    return grouped


def _index_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            'id': int(segment['seg_id']),
            'normalized_text': segment.get('normalized_text') or normalize_light(segment['raw_text']),
            'page_number': segment.get('page_number'),
            'segment_number': segment.get('segment_number', 1),
        }
        for segment in segments
    ]


def load_or_reconcile_index(
    raw_segments: list[dict[str, Any]],
    corpus_version: str,
    corpus_fingerprint: str,
    index_dir: Path | None = None,
    bm25_k1: float = 1.2,
    bm25_b: float = 0.75,
) -> tuple[LocalDiskRetrievalIndex, dict[str, int | bool | str]]:
    """Load a compatible index or reconcile documents and atomically save it.

    An unreadable/corrupt or old-schema directory is never used for retrieval; a
    clean in-memory index is built from the supplied corpus rows and promoted only
    after a successful full save.
    """
    target = Path(index_dir or config.RETRIEVAL_INDEX_DIR)
    expected_segment_fp = segment_fingerprint(raw_segments)
    grouped = _group_by_document(raw_segments)
    expected_doc_fp = {doc_id: _document_fingerprint(items) for doc_id, items in grouped.items()}
    index = LocalDiskRetrievalIndex(
        index_dir=target,
        corpus_version=corpus_version,
        fingerprint=corpus_fingerprint,
        segment_fingerprint=expected_segment_fp,
        normalization_version=NORMALIZATION_VERSION,
        bm25_k1=bm25_k1,
        bm25_b=bm25_b,
    )
    loaded = target.exists() and index.load(target)
    compatible_schema = loaded and index.index_version == INDEX_SCHEMA_VERSION
    compatible_normalization = loaded and index.normalization_version == NORMALIZATION_VERSION
    rebuilt = False
    changed_documents = 0

    if not compatible_schema or not compatible_normalization:
        index = LocalDiskRetrievalIndex(
            index_dir=target,
            corpus_version=corpus_version,
            fingerprint=corpus_fingerprint,
            segment_fingerprint=expected_segment_fp,
            normalization_version=NORMALIZATION_VERSION,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )
        for doc_id, items in grouped.items():
            index.add_document(doc_id, _index_segments(items), expected_doc_fp[doc_id])
        rebuilt = True
        changed_documents = len(grouped)
    else:
        # Reconcile source additions, edits, retirements and missing documents.
        for doc_id in list(index.doc_to_segments):
            if doc_id not in grouped:
                index.remove_document(doc_id)
                changed_documents += 1
        for doc_id, items in grouped.items():
            if index.document_fingerprints.get(doc_id) != expected_doc_fp[doc_id]:
                index.add_document(doc_id, _index_segments(items), expected_doc_fp[doc_id])
                changed_documents += 1

    changed = (
        rebuilt
        or changed_documents > 0
        or index.corpus_version != corpus_version
        or index.fingerprint != corpus_fingerprint
        or index.segment_fingerprint != expected_segment_fp
        or index.bm25_k1 != float(bm25_k1)
        or index.bm25_b != float(bm25_b)
    )
    index.corpus_version = corpus_version
    index.fingerprint = corpus_fingerprint
    index.segment_fingerprint = expected_segment_fp
    index.normalization_version = NORMALIZATION_VERSION
    index.bm25_k1 = float(bm25_k1)
    index.bm25_b = float(bm25_b)
    if changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        index.save(target)

    return index, {
        'loaded_from_disk': bool(loaded and not rebuilt),
        'rebuilt': rebuilt,
        'changed_documents': changed_documents,
        'index_dir': str(target),
        'segment_fingerprint': expected_segment_fp,
    }


def map_persistent_candidates(
    index: LocalDiskRetrievalIndex,
    query_text: str,
    segment_id_to_position: dict[int, int],
    top_k: int,
    allowed_doc_ids: set[int] | None = None,
) -> list[int]:
    """Return legacy corpus positions while preserving disk-index rank order."""
    segment_ids = index.search_candidates(query_text, top_k=top_k, allowed_doc_ids=allowed_doc_ids)
    return [segment_id_to_position[segment_id] for segment_id in segment_ids if segment_id in segment_id_to_position]
