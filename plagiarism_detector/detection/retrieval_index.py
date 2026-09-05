# -*- coding: utf-8 -*-
"""
محرك الفهرسة والاسترجاع المحلي الدائم للمجموعات المليونية (Scalable Persistent Retrieval Index):
- يوفر فهرساً مقلوباً ثنائي القناة (Dual-Channel Inverted Index: Rare Words + Morphological Char 3-Grams).
- خوارزمية استرجاع ثنائية المرحلة (Two-Stage Candidate Retrieval):
  * المرحلة الأولى: مسح مقلوب سريع بقناة الكلمات وIDF مع تعزيز التطابق الإحداثي (Coordinate Match Boost) لاستخراج أفضل K_internal (300 مرشح).
  * المرحلة الثانية: إعادة ترتيب معجمية خفيفة وسريعة (Fast Lexical Reranking) على المرشحين الداخليين.
  * المخرج النهائي: أعلى K <= 50 مرشحاً فقط وفق العقد الهندسي الصارم.
- حفظ واسترجاع الفهرس من وسائط التخزين المحلية مع بيان النزاهة index_manifest.json.
- تحديث تدريجي للمستندات (Incremental Updates) دون الحاجة لإعادة بناء الفهرس بالكامل.
- بناء محصن ذرياً ضد الانهيار (Crash-Safe Atomic Promotion via Temporary Staging).
- ارتباط وثيق مع إصدار قاعدة المراجع المعتمدة (Corpus Governance Version Coupling).
"""

import os
import io
import json
import math
import uuid
import time
import shutil
import hashlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, Any, List, Set, Union, Tuple

logger = logging.getLogger(__name__)

INDEX_SCHEMA_VERSION = "2.1.0"


class RetrievalIndex(ABC):
    """الواجهة القياسية الموحدة لفهارس استرجاع المرشحين."""

    @abstractmethod
    def search_candidates(
        self,
        query_input: Union[str, List[str]],
        top_k: int = 50,
        allowed_doc_ids: Optional[Set[int]] = None
    ) -> List[int]:
        """استرجاع أعلى top_k مقطع مرجعي مرشح للمطابقة الدقيقة."""
        pass

    @abstractmethod
    def add_document(self, doc_id: int, segments_data: List[Dict[str, Any]]) -> None:
        """إضافة مستند بمقاطعه تدريجياً إلى الفهرس."""
        pass

    @abstractmethod
    def remove_document(self, doc_id: int) -> None:
        """إزالة مستند ومقاطعه من الفهرس."""
        pass

    @abstractmethod
    def save(self, target_dir: Path) -> Path:
        """حفظ الفهرس وبيانه المعتمد على القرص."""
        pass

    @abstractmethod
    def load(self, index_dir: Path) -> bool:
        """تحميل الفهرس من القرص والتحقق من سلامة البصمات."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """استرجاع إحصائيات الفهرس."""
        pass


class LocalDiskRetrievalIndex(RetrievalIndex):
    """
    تطبيق الفهرس المقلوب الدائم عالي السعة والدقة للمجموعات المليونية.
    """

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        corpus_version: str = "REF-2026-000001",
        fingerprint: str = ""
    ):
        self.index_dir = Path(index_dir) if index_dir else None
        self.corpus_version = corpus_version
        self.fingerprint = fingerprint
        self.index_version = INDEX_SCHEMA_VERSION

        # القوائم المقلوبة: كلمة/ngram -> قائمة معرفات المقاطع
        self.word_postings: Dict[str, List[int]] = defaultdict(list)
        self.char_ngrams_postings: Dict[str, List[int]] = defaultdict(list)
        
        # فهرس العكسي: doc_id -> مجموعة معرفات المقاطع (للإزالة والتحديث التدريجي السريع)
        self.doc_to_segments: Dict[int, Set[int]] = defaultdict(set)
        
        # بيانات وصفية للمقاطع: seg_idx -> (doc_id, page_num, seg_num, word_count, words_set)
        self.segments_metadata: Dict[int, Dict[str, Any]] = {}
        
        self.total_segments: int = 0
        self.total_documents: int = 0
        self.built_at: Optional[str] = None
        self.is_stale: bool = False

    def add_document(self, doc_id: int, segments_data: List[Dict[str, Any]]) -> None:
        """إضافة مستند بمقاطعه تدريجياً وتحديث القوائم المقلوبة."""
        if doc_id in self.doc_to_segments:
            self.remove_document(doc_id)

        self.total_documents += 1
        doc_seg_ids = set()

        for seg in segments_data:
            seg_idx = seg['id']
            words = seg.get('normalized_words') or seg.get('normalized_text', '').split()
            norm_text = seg.get('normalized_text', '') or " ".join(words)
            page_num = seg.get('page_number')
            seg_num = seg.get('segment_number', 1)

            self.total_segments += 1
            doc_seg_ids.add(seg_idx)
            self.segments_metadata[seg_idx] = {
                'doc_id': doc_id,
                'page_number': page_num,
                'segment_number': seg_num,
                'word_count': len(words),
                'words': list(set(words))
            }

            # 1. القناة المعجمية (الكلمات النادرة بطول 3 أحرف فأكثر)
            for w in set(words):
                if len(w) >= 3:
                    self.word_postings[w].append(seg_idx)

            # 2. القناة المورفولوجية (Char 3-grams)
            clean_t = "".join(c for c in norm_text if c != " ")
            if len(clean_t) >= 3:
                cngs = set(clean_t[i:i+3] for i in range(len(clean_t) - 2))
                for cng in cngs:
                    self.char_ngrams_postings[cng].append(seg_idx)

        self.doc_to_segments[doc_id] = doc_seg_ids

    def remove_document(self, doc_id: int) -> None:
        """إزالة مستند ومقاطعه من القوائم المقلوبة تدريجياً."""
        if doc_id not in self.doc_to_segments:
            return

        seg_ids = self.doc_to_segments[doc_id]
        for seg_idx in seg_ids:
            if seg_idx in self.segments_metadata:
                del self.segments_metadata[seg_idx]
                self.total_segments = max(0, self.total_segments - 1)

            # تنظيف القوائم المقلوبة
            for word, p_list in list(self.word_postings.items()):
                if seg_idx in p_list:
                    p_list.remove(seg_idx)
                    if not p_list:
                        del self.word_postings[word]

            for cng, p_list in list(self.char_ngrams_postings.items()):
                if seg_idx in p_list:
                    p_list.remove(seg_idx)
                    if not p_list:
                        del self.char_ngrams_postings[cng]

        del self.doc_to_segments[doc_id]
        self.total_documents = max(0, self.total_documents - 1)

    def search_candidates(
        self,
        query_input: Union[str, List[str]],
        top_k: int = 50,
        allowed_doc_ids: Optional[Set[int]] = None
    ) -> List[int]:
        """
        استرجاع المرشحين ثنائي المرحلة عالي الدقة والسرعة:
        - المرحلة 1: تصفية القوائم المقلوبة واحتساب أوزان BM25-IDF وتعزيز التطابق الإحداثي (Coordinate Boost).
        - استخراج أفضل K_internal (حتى 300 مرشح داخلي).
        - المرحلة 2: إعادة ترتيب معجمية سريعة (Fast Lexical Jaccard Reranking).
        - إرجاع أعلى K <= 50 مرشحاً فقط.
        """
        if isinstance(query_input, list):
            words = query_input
            query_str = " ".join(query_input)
        else:
            query_str = str(query_input)
            words = query_str.split()

        scores: Dict[int, float] = defaultdict(float)
        matched_terms_count: Dict[int, int] = defaultdict(int)
        n_total = max(self.total_segments, 1)

        # 1. المرحلة الأولى: استعلام القناة المعجمية (الكلمات)
        q_words = [w for w in set(words) if len(w) >= 3 and w in self.word_postings]
        # ترتيب الكلمات بالندرة (أقل تردد أولاً)
        q_words.sort(key=lambda w: len(self.word_postings[w]))

        # تشذيب الكلمات فائقة الشيوعية (>45% من الكوربس في المجموعات الكبيرة)
        max_df = int(n_total * 0.45) if n_total > 1000 else n_total + 1
        active_words = [w for w in q_words if len(self.word_postings[w]) <= max_df] or q_words

        for w in active_words:
            postings = self.word_postings[w]
            df = len(postings)
            # Robertson-Sparck-Jones BM25 IDF
            idf_weight = math.log(1.0 + ((n_total - df + 0.5) / (df + 0.5)))
            for seg_idx in postings:
                if allowed_doc_ids is not None:
                    meta = self.segments_metadata.get(seg_idx)
                    if not meta or meta['doc_id'] not in allowed_doc_ids:
                        continue
                scores[seg_idx] += idf_weight
                matched_terms_count[seg_idx] += 1

        # 2. دعم القناة المورفولوجية للكلمات النادرة جداً أو القصيرة عند قلة المرشحين
        if len(scores) < 20:
            clean_q = "".join(c for c in query_str if c != " ")
            if len(clean_q) >= 3:
                q_cngs = set(clean_q[i:i+3] for i in range(len(clean_q) - 2))
                for cng in q_cngs:
                    if cng in self.char_ngrams_postings:
                        postings = self.char_ngrams_postings[cng]
                        df = len(postings)
                        if df <= max_df:
                            idf_weight = math.log(1.0 + ((n_total - df + 0.5) / (df + 0.5)))
                            for seg_idx in postings:
                                if allowed_doc_ids is not None:
                                    meta = self.segments_metadata.get(seg_idx)
                                    if not meta or meta['doc_id'] not in allowed_doc_ids:
                                        continue
                                scores[seg_idx] += 0.5 * idf_weight
                                matched_terms_count[seg_idx] += 1

        if not scores:
            return []

        # تطبيق التعزيز الإحداثي (Coordinate Match Boost): المرشح المتطابق في عدة مصطلحات يُضاعف وزنه
        for seg_idx, count in matched_terms_count.items():
            if count > 1:
                scores[seg_idx] *= (1.0 + 1.5 * (count - 1))

        # اقتطاع مرشحي المرحلة الأولى (Internal Top 300)
        internal_k = min(300, len(scores))
        top_candidates = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)[:internal_k]

        # ─── المرحلة الثانية: إعادة الترتيب المعجمية الخفيفة (Stage 2 Reranking) ───
        query_word_set = set(words)
        reranked_pool = []

        for seg_idx in top_candidates:
            meta = self.segments_metadata.get(seg_idx)
            cand_words = set(meta['words']) if meta and 'words' in meta else set()
            
            if cand_words and query_word_set:
                inter = len(query_word_set & cand_words)
                union = len(query_word_set | cand_words)
                lexical_sim = inter / union if union > 0 else 0.0
            else:
                lexical_sim = 0.0

            final_retrieval_score = scores[seg_idx] + 5.0 * lexical_sim
            reranked_pool.append((seg_idx, final_retrieval_score))

        # الترتيب النهائي واقتطاع أعلى top_k فقط (K <= 50)
        reranked_pool.sort(key=lambda x: x[1], reverse=True)
        final_top = [x[0] for x in reranked_pool[:top_k]]
        return final_top

    def save(self, target_dir: Path) -> Path:
        """
        حفظ الفهرس ذرياً على القرص مع احتساب وتوثيق بصمة البيان.
        """
        target_dir = Path(target_dir).resolve()
        staging_dir = target_dir.parent / f"_build_{uuid.uuid4().hex[:8]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. حفظ القوائم المقلوبة للمفردات
            words_data = {w: p for w, p in self.word_postings.items()}
            with open(staging_dir / "postings_words.json", "w", encoding="utf-8") as f:
                json.dump(words_data, f)

            # 2. حفظ القوائم المقلوبة للحروف
            cng_data = {c: p for c, p in self.char_ngrams_postings.items()}
            with open(staging_dir / "postings_cng.json", "w", encoding="utf-8") as f:
                json.dump(cng_data, f)

            # 3. حفظ بيانات المقاطع
            meta_data = {str(k): v for k, v in self.segments_metadata.items()}
            with open(staging_dir / "segments_metadata.json", "w", encoding="utf-8") as f:
                json.dump(meta_data, f)

            # 4. حفظ فهرس المستندات
            doc_data = {str(k): list(v) for k, v in self.doc_to_segments.items()}
            with open(staging_dir / "doc_to_segments.json", "w", encoding="utf-8") as f:
                json.dump(doc_data, f)

            # 5. احتساب البصمات الإلكترونية للملفات
            manifest_data = {
                "index_version": self.index_version,
                "corpus_version": self.corpus_version,
                "corpus_fingerprint": self.fingerprint,
                "built_at": datetime_utcnow_iso(),
                "total_documents": self.total_documents,
                "total_segments": self.total_segments,
                "vocabulary_size": len(self.word_postings),
                "char_ngrams_size": len(self.char_ngrams_postings),
                "checksums": {
                    "postings_words": compute_file_hash(staging_dir / "postings_words.json"),
                    "postings_cng": compute_file_hash(staging_dir / "postings_cng.json"),
                    "segments_metadata": compute_file_hash(staging_dir / "segments_metadata.json"),
                    "doc_to_segments": compute_file_hash(staging_dir / "doc_to_segments.json"),
                }
            }

            with open(staging_dir / "index_manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, ensure_ascii=False, indent=2)

            # 6. الترقية الذرية للمجلد النهائي
            if target_dir.exists():
                old_bak = target_dir.parent / f"_old_idx_{uuid.uuid4().hex[:6]}"
                os.replace(str(target_dir), str(old_bak))
                os.replace(str(staging_dir), str(target_dir))
                shutil.rmtree(str(old_bak), ignore_errors=True)
            else:
                os.replace(str(staging_dir), str(target_dir))

            self.index_dir = target_dir
            self.built_at = manifest_data["built_at"]
            logger.info(f"تم حفظ الفهرس الدائم بنجاح في: {target_dir} ({self.total_segments} مقطع).")
            return target_dir

        finally:
            if staging_dir.exists():
                shutil.rmtree(str(staging_dir), ignore_errors=True)

    def load(self, index_dir: Path) -> bool:
        """
        تحميل الفهرس من القرص والتحقق من صحة البصمات والبيان.
        """
        index_dir = Path(index_dir).resolve()
        manifest_file = index_dir / "index_manifest.json"
        if not manifest_file.exists():
            logger.warning(f"بيان الفهرس index_manifest.json غير موجود في {index_dir}")
            return False

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            # مطابقة بصمات الملفات
            checksums = manifest.get("checksums", {})
            for fname, exp_hash in checksums.items():
                p = index_dir / f"{fname}.json"
                if not p.exists() or compute_file_hash(p) != exp_hash:
                    logger.error(f"فشل مطابقة بصمة ملف الفهرس: {p}")
                    return False

            # تحميل البيانات
            with open(index_dir / "postings_words.json", "r", encoding="utf-8") as f:
                w_raw = json.load(f)
                self.word_postings = defaultdict(list, {k: list(v) for k, v in w_raw.items()})

            with open(index_dir / "postings_cng.json", "r", encoding="utf-8") as f:
                c_raw = json.load(f)
                self.char_ngrams_postings = defaultdict(list, {k: list(v) for k, v in c_raw.items()})

            with open(index_dir / "segments_metadata.json", "r", encoding="utf-8") as f:
                m_raw = json.load(f)
                self.segments_metadata = {int(k): v for k, v in m_raw.items()}

            with open(index_dir / "doc_to_segments.json", "r", encoding="utf-8") as f:
                d_raw = json.load(f)
                self.doc_to_segments = defaultdict(set, {int(k): set(v) for k, v in d_raw.items()})

            self.index_version = manifest.get("index_version", INDEX_SCHEMA_VERSION)
            self.corpus_version = manifest.get("corpus_version", "")
            self.fingerprint = manifest.get("corpus_fingerprint", "")
            self.total_documents = manifest.get("total_documents", len(self.doc_to_segments))
            self.total_segments = manifest.get("total_segments", len(self.segments_metadata))
            self.built_at = manifest.get("built_at")
            self.index_dir = index_dir
            self.is_stale = False

            logger.info(f"تم تحميل الفهرس بنجاح من {index_dir} ({self.total_segments} مقطع، إصدار: {self.corpus_version}).")
            return True

        except Exception as e:
            logger.error(f"خطأ أثناء تحميل الفهرس من القرص: {e}", exc_info=True)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """استرجاع إحصائيات الفهرس."""
        return {
            "index_version": self.index_version,
            "corpus_version": self.corpus_version,
            "corpus_fingerprint": self.fingerprint,
            "total_documents": self.total_documents,
            "total_segments": self.total_segments,
            "vocabulary_size": len(self.word_postings),
            "char_ngrams_size": len(self.char_ngrams_postings),
            "built_at": self.built_at,
            "is_stale": self.is_stale,
            "index_dir": str(self.index_dir) if self.index_dir else None
        }


def datetime_utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def compute_file_hash(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
