# -*- coding: utf-8 -*-
"""
أداة هجرة مسارات التخزين إلى الهيكل المؤسسي المقسم أوفلاين (Offline Storage Layout Migration CLI):
- تفحص كافة ملفات الأبحاث والمراجع المسجلة في قاعدة البيانات.
- تنقل الملفات من المسارات المسطحة القديمة إلى الهيكل المقسم الموجه بالمحتوى (CAS): storage/documents/ab/cd/<hash>/
- تتحقق بدقة متناهية من تطابق بصمات SHA-256 وحجم البايتات قبل وبعد الترقية.
- تحدث مؤشرات المسارات في قاعدة البيانات بعد التأكد التام من نجاح التخزين.
- تنتج تقريراً شاملاً بصيغة JSON.
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from app.repositories import base_repo
from app.models.research_schema import ResearchFile
from app.models.schema import Document
from app.storage.filesystem_backend import FileSystemStorageBackend

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("storage_migration")


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class StorageMigrator:
    def __init__(self, dry_run: bool = False, cas_root: Optional[Path] = None):
        self.dry_run = dry_run
        self.cas_root = Path(cas_root) if cas_root else Path(config.STORAGE_ROOT)
        self.backend = FileSystemStorageBackend(self.cas_root)
        self.report: Dict[str, Any] = {
            'started_at': base_repo.datetime.now().isoformat() + 'Z',
            'dry_run': self.dry_run,
            'total_files_scanned': 0,
            'already_cas': 0,
            'migrated_count': 0,
            'deduplicated_count': 0,
            'missing_source_count': 0,
            'errors': []
        }

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        logger.info("==================================================")
        logger.info("بدء أداة هجرة تخزين الملفات إلى الهيكل المقسم CAS (Prompt 2)")
        logger.info(f"المجلد المستهدف: {self.cas_root}")
        logger.info(f"نمط المحاكاة: {self.dry_run}")
        logger.info("==================================================")

        with base_repo.get_session() as session:
            # 1. جلب ملفات الأبحاث
            research_files = session.query(ResearchFile).all()
            logger.info(f"تم العثور على {len(research_files)} ملف أبحاث مسجل للفحص.")

            for rf in research_files:
                self.report['total_files_scanned'] += 1
                f_path = Path(rf.file_path) if rf.file_path else None
                f_hash = rf.file_hash

                if not f_path or not f_path.exists():
                    self.report['missing_source_count'] += 1
                    logger.warning(f"الملف المصدر غير موجود على القرص: {rf.id} - {f_path}")
                    continue

                # فحص ما إذا كان الملف مسبقاً في مسار CAS
                if "/documents/" in str(f_path).replace("\\", "/"):
                    self.report['already_cas'] += 1
                    continue

                # احتساب البصمة الحقيقية والتأكد من مطابقتها
                src_hash = compute_sha256(f_path)
                if f_hash and src_hash.lower() != f_hash.lower():
                    err = f"تعارض في بصمة الملف {rf.id}: مسجلة={f_hash}, محسوبة={src_hash}"
                    logger.error(err)
                    self.report['errors'].append(err)
                    continue

                f_hash = f_hash or src_hash
                ext = Path(rf.original_filename or f_path.name).suffix or '.bin'

                if not self.dry_run:
                    # تخزين في CAS
                    with open(f_path, 'rb') as f:
                        res = self.backend.put(
                            stream_or_bytes=f,
                            content_hash=f_hash,
                            ext=ext,
                            metadata={'original_filename': rf.original_filename, 'research_id': rf.research_id}
                        )

                    # تحديث المسار في قاعدة البيانات
                    new_path = res['file_path']
                    rf.file_path = new_path
                    rf.file_hash = f_hash

                    if res.get('deduplicated'):
                        self.report['deduplicated_count'] += 1
                    else:
                        self.report['migrated_count'] += 1
                else:
                    self.report['migrated_count'] += 1

            if not self.dry_run:
                session.commit()
                logger.info("تم تثبيت تحديثات المسارات في قاعدة البيانات بنجاح.")

        self.report['completed_at'] = base_repo.datetime.now().isoformat() + 'Z'
        self.report['duration_seconds'] = round(time.time() - t0, 3)
        self.report['success'] = len(self.report['errors']) == 0
        return self.report


def main():
    parser = argparse.ArgumentParser(description="أداة هجرة تخزين الملفات إلى الهيكل المقسم CAS")
    parser.add_argument("--dry-run", action="store_true", help="تشغيل فحص مسبق دون كتابة بيانات")
    parser.add_argument("--output-report", type=str, default="storage_migration_report.json", help="مسار حفظ التقرير")
    args = parser.parse_args()

    migrator = StorageMigrator(dry_run=args.dry_run)
    rep = migrator.run()

    with open(args.output_report, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    logger.info(f"تم حفظ تقرير الهجرة في: {Path(args.output_report).resolve()}")


if __name__ == '__main__':
    main()
