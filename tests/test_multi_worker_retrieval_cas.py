# -*- coding: utf-8 -*-
"""
Concurrent retrieval index and shared CAS storage tests across multiple workers.
Verifies thread/process safety for concurrent reads and atomic writes.
"""

import os
import tempfile
import hashlib
from concurrent.futures import ThreadPoolExecutor
from plagiarism_detector.detection.retrieval_index import LocalDiskRetrievalIndex
from app.storage.filesystem_backend import FileSystemStorageBackend


def test_concurrent_retrieval_reads():
    """Verify that multiple concurrent workers can query the same loaded retrieval index safely."""
    index = LocalDiskRetrievalIndex(corpus_version="CONC-CORPUS-01", fingerprint="fp-conc")
    
    # Populate index with sample documents
    for doc_id in range(1, 20):
        segs = [
            {
                'id': doc_id * 10 + s,
                'normalized_words': ['الذكاء', 'الاصطناعي', 'البحث', 'العلمي', f'كلمة_{doc_id}'],
                'page_number': 1,
                'segment_number': s
            }
            for s in range(1, 5)
        ]
        index.add_document(doc_id, segs)

    def worker_query(q_id: int):
        words = ['الذكاء', 'الاصطناعي', 'البحث', f'كلمة_{q_id % 10 + 1}']
        candidates = index.search_candidates(words, top_k=50)
        assert len(candidates) <= 50
        return len(candidates)

    # Execute 20 concurrent queries
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker_query, range(20)))

    assert len(results) == 20
    for count in results:
        assert count > 0


def test_concurrent_cas_storage_reads_and_writes():
    """Verify that multiple concurrent workers can write and read from shared CAS storage safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = FileSystemStorageBackend(tmpdir)

        def worker_task(idx: int):
            content = f"وثيقة تجريبية للعامل رقم {idx}".encode('utf-8')
            c_hash = hashlib.sha256(content).hexdigest()
            res = backend.put(content, c_hash, ext='.txt', metadata={"worker_id": idx})
            assert res['success'] is True
            assert backend.exists(c_hash) is True
            read_bytes = backend.get(c_hash)
            assert read_bytes == content
            return c_hash

        with ThreadPoolExecutor(max_workers=4) as executor:
            hashes = list(executor.map(worker_task, range(15)))

        assert len(hashes) == 15
        assert len(set(hashes)) == 15
