# -*- coding: utf-8 -*-
"""
أداة إعادة بناء فهرس الاسترجاع المقلوب أوفلاين (Offline Retrieval Index Rebuilder CLI):
- تستعلم قاعدة المراجع المعتمدة من قاعدة البيانات.
- تبني الفهرس المقلوب ثنائي القناة (Words + Char 3-grams) في مجلد staging مؤقت.
- تتحقق من اكتمال وبصمات القوائم المقلوبة والبيان index_manifest.json.
- تنفذ الترقية الذرية (Atomic Promotion) إلى مجلد الفهرس النهائي وتحدث سجل حالة الفهرس في قاعدة البيانات.
"""

import sys
import time
import argparse
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from app.repositories import base_repo
from app.models.schema import Document, DocumentSegment, IndexStateRecord, ReferenceCorpusVersion
from plagiarism_detector.detection.retrieval_index import LocalDiskRetrievalIndex

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("rebuild_index")


def rebuild_index(dry_run: bool = False, output_dir: Path = None) -> dict:
    t0 = time.time()
    logger.info("==================================================")
    logger.info("بدء أداة إعادة بناء فهرس الاسترجاع المقلوب (Prompt 2)")
    logger.info("==================================================")

    target_root = output_dir or (Path(config.STORAGE_ROOT) / "retrieval_index")

    with base_repo.get_session() as session:
        # 1. جلب أحدث إصدار لقاعدة المراجع
        latest_v = (
            session.query(ReferenceCorpusVersion)
            .order_by(ReferenceCorpusVersion.id.desc())
            .first()
        )
        c_ver = latest_v.version_identifier if latest_v else "REF-2026-000001"
        c_fingerprint = latest_v.fingerprint if latest_v else ""

        # 2. جلب المستندات النشطة فقط
        docs = session.query(Document).filter(Document.current_status == 'active').all()
        doc_count = len(docs)
        logger.info(f"إصدار قاعدة المراجع: {c_ver} | عدد المراجع النشطة: {doc_count}")

        if dry_run:
            logger.info("نمط المحاكاة (Dry-Run) مفعل. لم يتم تعديل الفهرس على القرص.")
            return {
                'success': True,
                'dry_run': True,
                'corpus_version': c_ver,
                'document_count': doc_count,
                'duration_seconds': round(time.time() - t0, 3)
            }

        # 3. بناء الفهرس
        index = LocalDiskRetrievalIndex(corpus_version=c_ver, fingerprint=c_fingerprint)
        total_segments = 0

        for doc in docs:
            segs = session.query(DocumentSegment).filter(DocumentSegment.document_id == doc.id).all()
            seg_list = []
            for s in segs:
                seg_list.append({
                    'id': s.id,
                    'normalized_text': s.normalized_text,
                    'page_number': s.page_number,
                    'segment_number': s.segment_number
                })
            index.add_document(doc.id, seg_list)
            total_segments += len(seg_list)

        logger.info(f"تمت فهرسة {total_segments} مقطع عبر {doc_count} مستند بنجاح.")

        # 4. الحفظ الذري على القرص
        dest_dir = target_root / c_ver
        final_path = index.save(dest_dir)

        # 5. تحديث سجل حالة الفهرس في قاعدة البيانات
        idx_rec = IndexStateRecord(
            state='current',
            index_corpus_version=c_ver,
            built_at=base_repo.datetime.now(),
            total_documents=doc_count,
            total_segments=total_segments
        )
        session.add(idx_rec)
        session.commit()

        dur = round(time.time() - t0, 3)
        logger.info(f"اكتمل بناء وحفظ الفهرس بنجاح في {dur} ثانية: {final_path}")

        return {
            'success': True,
            'dry_run': False,
            'corpus_version': c_ver,
            'document_count': doc_count,
            'segment_count': total_segments,
            'index_path': str(final_path),
            'duration_seconds': dur
        }


def main():
    parser = argparse.ArgumentParser(description="أداة إعادة بناء فهرس الاسترجاع المقلوب أوفلاين")
    parser.add_argument("--dry-run", action="store_true", help="تشغيل فحص مسبق دون كتابة الفهرس على القرص")
    parser.add_argument("--output-dir", type=str, default=None, help="مسار مجلد حفظ الفهرس")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    res = rebuild_index(dry_run=args.dry_run, output_dir=out_dir)
    print(res)


if __name__ == '__main__':
    main()
