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
    if not model_path.exists():
        return {
            'available': False,
            'reason': (
                f"مجلد النموذج الدلالي المحلي غير موجود: {model_path}. "
                "المنظومة تعمل 100% أوفلاين ولن تقوم بتحميل أي ملفات من الإنترنت تلقائياً. "
                "يرجى وضع ملفات نموذج FastEmbed/ONNX يدوياً في هذا المسار لتفعيل الكشف الدلالي."
            )
        }

    return {
        'available': True,
        'reason': f"النموذج الدلالي المحلي مثبت ومتاح في المسار: {model_path}"
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
    if not model_path.exists():
        logger.info(f"النموذج الدلالي غير مثبت محلياً في {model_path} - العمل مستمر بنمط TF-IDF + Jaccard دون إنترنت.")
        _IS_AVAILABLE = False
        return None

    try:
        from fastembed import TextEmbedding
        # تحميل النموذج من المسار المحلي الحصري
        _EMBEDDER = TextEmbedding(
            model_name=str(model_path),
            cache_dir=str(config.MODELS_DIR),
            local_files_only=True
        )
        _IS_AVAILABLE = True
        return _EMBEDDER
    except Exception as e:
        logger.warning(f"تعذر تحميل النموذج الدلالي من المسار المحلي {model_path}: {e}")
        _IS_AVAILABLE = False
        return None


def compute_embeddings(texts: list[str]) -> Optional[np.ndarray]:
    """حساب متجهات التضمين الدلالي دفعة واحدة (Batch Inference)."""
    embedder = get_embedder()
    if embedder is None or not texts:
        return None

    try:
        # FastEmbed يرجع مولداً لمصفوفات numpy
        embeddings = list(embedder.embed(texts))
        return np.array(embeddings)
    except Exception as e:
        logger.warning(f"فشل حساب التضمين الدلالي: {e}")
        return None


def match_semantic_similarity(
    query_text: str,
    candidate_indices: list[int],
    corpus_texts: list[str],
    corpus_embeddings: Optional[np.ndarray],
    threshold: float = 0.70
) -> Optional[tuple[int, float, str]]:
    """
    مقارنة دلالية بين جملة البحث والمرشحين.
    ترجع: (أفضل مؤشر مرشح، درجة التشابه من 0 إلى 1، وسم نوع التطابق).
    """
    if corpus_embeddings is None or not candidate_indices:
        return None

    q_embed = compute_embeddings([query_text])
    if q_embed is None:
        return None

    try:
        q_vec = q_embed[0]
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
