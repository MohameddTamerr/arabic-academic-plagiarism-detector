# -*- coding: utf-8 -*-
"""
المرحلة C: محرك التشابه الدلالي المحلي فائق الخفة (Stage C - Lightweight Offline Semantic Matcher):
- اختياري بالكامل (قابل للتفعيل أو التعطيل عبر الإعدادات ENABLE_SEMANTIC_MODEL).
- يعمل 100% أوفلاين على المعالج (CPU-Only) عبر FastEmbed / ONNX Runtime بدون استهلاك للإنترنت.
- يُخزِّن التضمينات (Embeddings Cache) محلياً لتفادي إعادة الحساب.
- يُوسم دائمًا بـ "تشابه دلالي / احتمال إعادة صياغة" ولا يُعتبر وحده سرقة مؤكدة.
"""

import os
import logging
from typing import Optional
import numpy as np

import config

logger = logging.getLogger(__name__)

_EMBEDDER = None
_IS_AVAILABLE = False


def _required_model_files() -> list:
    """Return the exact bundled assets required for air-gapped inference."""
    snapshot_dir = config.SEMANTIC_MODEL_PATH / 'snapshots'
    model_root = snapshot_dir / config.SEMANTIC_MODEL_REVISION
    return [
        model_root / config.SEMANTIC_MODEL_FILE,
        model_root / 'config.json',
        model_root / 'tokenizer.json',
        model_root / 'tokenizer_config.json',
        model_root / 'special_tokens_map.json',
        model_root / 'sentencepiece.bpe.model',
    ]


def check_semantic_model_availability() -> dict:
    """
    التحقق من توفر حزم ونماذج التضمين الدلالي أوفلاين على القرص المحلي حصراً.
    يمنع منعاً باتاً تنزيل أي نموذج تلقائياً من الإنترنت أثناء التشغيل.
    """
    try:
        import fastembed
    except ImportError:
        return {
            'available': False,
            'reason': 'مكتبة fastembed غير مثبتة في البيئة الحالية (ثبت requirements-semantic.txt عند الرغبة).'
        }

    model_path = config.SEMANTIC_MODEL_PATH
    missing_files = [path for path in _required_model_files() if not path.is_file()]
    if missing_files:
        return {
            'available': False,
            'reason': (
                f"ملفات النموذج الدلالي المحلي غير مكتملة: {model_path}. "
                "المنظومة تعمل 100% أوفلاين ولن تقوم بتحميل أي ملفات من الإنترنت تلقائياً. "
                "يرجى وضع ملفات نموذج FastEmbed/ONNX يدوياً في هذا المسار لتفعيل الكشف الدلالي."
            ),
            'missing_files': [str(path) for path in missing_files],
        }

    return {
        'available': True,
        'reason': f"النموذج الدلالي المحلي مثبت ومتاح في المسار: {model_path}",
        'identifier': config.SEMANTIC_MODEL_IDENTIFIER,
        'version': config.SEMANTIC_MODEL_VERSION,
        'backend': 'FastEmbed / ONNX Runtime CPU INT8',
        'offline': True,
    }


def get_embedder():
    """
    تهيئة نموذج FastEmbed أوفلاين فقط إذا كانت ملفاته مثبتة محلياً على القرص.
    لا يقوم بالاتصال بالإنترنت أو Hugging Face إطلاقاً.
    """
    global _EMBEDDER, _IS_AVAILABLE
    if _EMBEDDER is not None:
        return _EMBEDDER

    # فحص صارم: إذا لم تكن ملفات النموذج موجودة على القرص، لا تحاول التحميل من الإنترنت
    model_path = config.SEMANTIC_MODEL_PATH
    if not check_semantic_model_availability().get('available'):
        logger.info(f"النموذج الدلالي غير مثبت محلياً في {model_path} - العمل مستمر بنمط TF-IDF + Jaccard دون إنترنت.")
        _IS_AVAILABLE = False
        return None

    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        # Register the bundled generic INT8 E5 build explicitly.  FastEmbed's
        # built-in catalogue does not currently include multilingual-e5-small.
        try:
            TextEmbedding.add_custom_model(
                model=config.SEMANTIC_MODEL_NAME,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf=config.SEMANTIC_MODEL_IDENTIFIER),
                dim=384,
                model_file=config.SEMANTIC_MODEL_FILE,
                description='Offline generic INT8 multilingual E5 small',
                license='mit',
                size_in_gb=0.14,
            )
        except ValueError as exc:
            if 'already registered' not in str(exc).lower():
                raise

        _EMBEDDER = TextEmbedding(
            model_name=config.SEMANTIC_MODEL_NAME,
            cache_dir=str(config.MODELS_DIR),
            local_files_only=True,
            threads=max(1, min(4, os.cpu_count() or 1)),
        )
        _IS_AVAILABLE = True
        return _EMBEDDER
    except Exception as e:
        logger.warning(f"تعذر تحميل النموذج الدلالي من المسار المحلي {model_path}: {e}")
        _IS_AVAILABLE = False
        return None


def compute_embeddings(texts: list[str], role: str = 'query') -> Optional[np.ndarray]:
    """Compute normalized E5 embeddings with the required query/passage prefix."""
    embedder = get_embedder()
    if embedder is None or not texts:
        return None
    try:
        if role not in {'query', 'passage'}:
            raise ValueError("role must be either 'query' or 'passage'")
        prefix = (
            config.SEMANTIC_QUERY_PREFIX
            if role == 'query'
            else config.SEMANTIC_PASSAGE_PREFIX
        )
        prepared_texts = [
            text if str(text).startswith(prefix) else f'{prefix}{text}'
            for text in texts
        ]
        # FastEmbed returns an iterator of normalized NumPy vectors.
        embeddings = list(embedder.embed(prepared_texts, batch_size=16))
        return np.array(embeddings)
    except Exception as e:
        logger.warning(f"فشل حساب التضمين الدلالي: {e}")
        return None


def rank_semantic_candidates(
    query_embedding: Optional[np.ndarray],
    corpus_embeddings: Optional[np.ndarray],
    candidate_indices: Optional[list[int]] = None,
    top_k: int = 50,
) -> list[tuple[int, float]]:
    """Rank semantic candidates without applying a plagiarism threshold.

    This is retrieval evidence only.  It intentionally returns cosine scores
    separately from the Stage C acceptance threshold and never creates spans.
    Supplying no candidate indices ranks the complete local corpus, allowing a
    semantic paraphrase to be recovered even when BM25 has no lexical candidate.
    """
    if query_embedding is None or corpus_embeddings is None or top_k <= 0:
        return []
    try:
        corpus = np.asarray(corpus_embeddings)
        if corpus.ndim != 2 or not len(corpus):
            return []
        indices = np.arange(len(corpus), dtype=np.intp) if candidate_indices is None else np.asarray(candidate_indices, dtype=np.intp)
        if not len(indices):
            return []
        q_vec = np.asarray(query_embedding)
        vectors = corpus[indices]
        norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(q_vec)
        norms[norms == 0] = 1e-10
        scores = (vectors @ q_vec) / norms
        # Stable tie-break by corpus position makes repeat reports reproducible.
        order = sorted(range(len(indices)), key=lambda local: (-float(scores[local]), int(indices[local])))
        return [(int(indices[local]), float(scores[local])) for local in order[:top_k]]
    except Exception as exc:
        logger.debug("تعذر ترتيب المرشحين الدلاليين: %s", exc)
        return []

def batch_match_semantic_similarity(
    query_embeddings: np.ndarray,
    candidate_indices: list[int],
    corpus_embeddings: Optional[np.ndarray],
    threshold: float = 0.70,
) -> list[Optional[tuple[int, float, str]]]:
    """
    Match a batch of query embeddings with the same exact cosine rule used by
    ``match_semantic_similarity``.

    The corpus slice and its norms are prepared once for the whole batch, then
    NumPy performs one matrix multiplication.  This preserves the selected
    candidate and threshold semantics while avoiding a full corpus scan for
    every individual document segment.
    """
    threshold = max(float(threshold), float(config.SEMANTIC_MODEL_MIN_SCORE))
    queries = np.asarray(query_embeddings)
    if queries.ndim == 1:
        queries = queries.reshape(1, -1)

    query_count = int(queries.shape[0]) if queries.ndim == 2 else 0
    if query_count == 0:
        return []
    if corpus_embeddings is None or not candidate_indices:
        return [None] * query_count

    try:
        candidate_array = np.asarray(candidate_indices, dtype=np.intp)
        candidate_vectors = np.asarray(corpus_embeddings)[candidate_array]
        if candidate_vectors.ndim != 2 or queries.shape[1] != candidate_vectors.shape[1]:
            return [None] * query_count

        dot_products = np.matmul(queries, candidate_vectors.T)
        query_norms = np.linalg.norm(queries, axis=1)
        candidate_norms = np.linalg.norm(candidate_vectors, axis=1)
        denominators = query_norms[:, None] * candidate_norms[None, :]
        denominators[denominators == 0] = 1e-10
        similarities = dot_products / denominators

        best_local_indices = np.argmax(similarities, axis=1)
        best_scores = similarities[np.arange(query_count), best_local_indices]
        results: list[Optional[tuple[int, float, str]]] = []
        for query_idx, (local_idx, score) in enumerate(zip(best_local_indices, best_scores)):
            numeric_score = float(score)
            # BLAS may differ from one-vector np.dot by a few last decimal
            # places. Re-run only threshold-borderline rows through the
            # established scalar path so classification cannot flip there.
            if abs(numeric_score - threshold) <= 1e-6:
                results.append(match_semantic_similarity(
                    query_text='',
                    candidate_indices=candidate_indices,
                    corpus_texts=[],
                    corpus_embeddings=corpus_embeddings,
                    threshold=threshold,
                    query_embedding=queries[query_idx],
                ))
                continue
            if numeric_score >= threshold:
                results.append((
                    int(candidate_array[int(local_idx)]),
                    numeric_score,
                    'SEMANTIC SIMILARITY / POSSIBLE PARAPHRASE',
                ))
            else:
                results.append(None)
        return results
    except Exception as e:
        logger.debug(f"خطأ في المقارنة الدلالية المجمعة: {e}")
        return [None] * query_count


def match_semantic_similarity(
    query_text: str,
    candidate_indices: list[int],
    corpus_texts: list[str],
    corpus_embeddings: Optional[np.ndarray],
    threshold: float = 0.70,
    query_embedding: Optional[np.ndarray] = None,
) -> Optional[tuple[int, float, str]]:
    """
    مقارنة دلالية بين جملة البحث والمرشحين.
    ترجع: (أفضل مؤشر مرشح، درجة التشابه من 0 إلى 1، وسم نوع التطابق).
    """
    threshold = max(float(threshold), float(config.SEMANTIC_MODEL_MIN_SCORE))
    if corpus_embeddings is None or not candidate_indices:
        return None

    if query_embedding is None:
        q_embed = compute_embeddings([query_text])
        if q_embed is None:
            return None
        query_embedding = q_embed[0]

    try:
        q_vec = query_embedding
        cand_vectors = corpus_embeddings[candidate_indices]

        # Cosine similarity للمتجهات الطبيعية
        dot_products = np.dot(cand_vectors, q_vec)
        norms = np.linalg.norm(cand_vectors, axis=1) * np.linalg.norm(q_vec)
        norms[norms == 0] = 1e-10
        sims = dot_products / norms

        best_cand_idx = int(np.argmax(sims))
        best_score = float(sims[best_cand_idx])

        if best_score >= threshold:
            global_idx = candidate_indices[best_cand_idx]
            return global_idx, best_score, 'SEMANTIC SIMILARITY / POSSIBLE PARAPHRASE'
    except Exception as e:
        logger.debug(f"خطأ في المقارنة الدلالية: {e}")

    return None
