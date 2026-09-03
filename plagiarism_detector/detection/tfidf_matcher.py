# -*- coding: utf-8 -*-
"""
المرحلة B: محرك كشف إعادة الصياغة اللفظية (Stage B - TF-IDF & Cosine Similarity Matcher):
- يستخدم أوزان TF-IDF مع الكلمات الثنائية (Word 1-2 N-Grams).
- يقيس تشابه جيب التمام (Cosine Similarity) بين متجهات الجمل.
- يُطبَّق فقط على قائمة المرشحين المسترجعة (Candidate Segments) لضمان السرعة الفائقة على المعالج.
"""

from typing import Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def match_lexical_paraphrase(
    query_norm_text: str,
    candidate_indices: list[int],
    corpus_norm_texts: list[str],
    threshold: float = 0.60,
    vectorizer: Optional[TfidfVectorizer] = None,
    corpus_tfidf_matrix = None
) -> Optional[tuple[int, float, str]]:
    """
    فحص إعادة الصياغة اللفظية باستخدام متجهات TF-IDF.
    يرجع: (أفضل مؤشر مرشح، درجة التشابه من 0 إلى 1، نوع التطابق).
    """
    if not candidate_indices or not query_norm_text.strip():
        return None

    # إذا كان لدينا مصفوفة TF-IDF مدربة مسبقاً
    if vectorizer is not None and corpus_tfidf_matrix is not None:
        try:
            q_vec = vectorizer.transform([query_norm_text])
            # استخراج متجهات المرشحين فقط
            cand_matrix = corpus_tfidf_matrix[candidate_indices]
            sims = cosine_similarity(q_vec, cand_matrix).flatten()

            best_local_idx = int(np.argmax(sims))
            best_score = float(sims[best_local_idx])

            if best_score >= threshold:
                best_global_idx = candidate_indices[best_local_idx]
                return best_global_idx, best_score, 'POSSIBLE PARAPHRASE'
        except Exception:
            pass

    # في حال عدم توفر مصفوفة جاهزة، نقوم بحساب TF-IDF محلي على المرشحين فقط
    cand_texts = [corpus_norm_texts[idx] for idx in candidate_indices]
    all_texts = [query_norm_text] + cand_texts

    try:
        local_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        matrix = local_vec.fit_transform(all_texts)
        q_vec = matrix[0:1]
        cands_matrix = matrix[1:]
        word_sims = cosine_similarity(q_vec, cands_matrix).flatten()

        # إضافة متجهات الحروف المورفولوجية char_wb للتعامل مع سوابق ولواحق الكلمات العربية
        try:
            char_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4), min_df=1)
            c_matrix = char_vec.fit_transform(all_texts)
            char_sims = cosine_similarity(c_matrix[0:1], c_matrix[1:]).flatten()
            sims = np.maximum(word_sims, 0.7 * word_sims + 0.3 * char_sims)
        except Exception:
            sims = word_sims

        best_local_idx = int(np.argmax(sims))
        best_score = float(sims[best_local_idx])

        if best_score >= threshold:
            best_global_idx = candidate_indices[best_local_idx]
            return best_global_idx, best_score, 'POSSIBLE PARAPHRASE'
    except Exception:
        pass

    return None
