# -*- coding: utf-8 -*-
"""
خدمة سلامة الملفات وكشف التكرار الرقمي (File Integrity & Duplicate Detection Service):
- حساب البصمة الرقمية SHA-256 للملفات عبر القراءة المجزأة (Streamed Hashing).
- توليد أسماء تخزين آمنة محصنة ضد هجمات مسارات الملفات (Path Traversal / Null Bytes / Reserved Names).
- كشف التكرار الدقيق للوثائق والأبحاث قبل بدء الفحص غير الضروري.
- حماية الخصوصية ومنع تسريب بيانات الأبحاث السابقة للمستخدمين غير المصرح لهم.
- فحص سلامة وتطابق الملفات المخزنة على الخادم مع بصماتها المسجلة.
"""

import os
import re
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List, Union

import config
from app.repositories import batch_repo, document_repo, report_repo
from app.services import audit_service
from app.security.permissions import Permission
from app.security.authorization import has_permission, can_view_research

logger = logging.getLogger(__name__)

# قائمة الأسماء المحجوزة في أنظمة التشغيل (Windows Device Names)
_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}


def compute_stream_sha256(file_input: Union[str, Path, Any], chunk_size: int = 65536) -> Tuple[str, int]:
    """
    حساب بصمة SHA-256 وحجم الملف عبر القراءة المتدفقة (Streamed) دون تحميل الملفات الكبيرة في الذاكرة.
    يقبل مسار ملف (str/Path) أو كائن ملف (FileStorage / BytesIO).
    يُعيد (sha256_hex_string, size_in_bytes).
    """
    hasher = hashlib.sha256()
    total_size = 0

    if isinstance(file_input, (str, Path)):
        file_path = Path(file_input)
        if not file_path.exists():
            raise FileNotFoundError(f"الملف غير موجود: {file_path}")
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
                total_size += len(chunk)
    else:
        # كائن ملف مفتوح أو مرفوع عبر Flask (FileStorage / BytesIO)
        stream = file_input.stream if hasattr(file_input, 'stream') else file_input
        # حفظ الموضع الحالي إن أمكن
        pos = stream.tell() if hasattr(stream, 'tell') else 0
        try:
            if hasattr(stream, 'seek'):
                stream.seek(0)
            while chunk := stream.read(chunk_size):
                if isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')
                hasher.update(chunk)
                total_size += len(chunk)
        finally:
            if hasattr(stream, 'seek'):
                stream.seek(pos)

    return hasher.hexdigest(), total_size


def get_safe_storage_filename(original_filename: str) -> str:
    """
    توليد اسم تخزين آمن ومحمي بالكامل على الخادم.
    - يزيل مسارات المجلدات والحركات الاحتيالية (../, absolute paths, Windows drive letters).
    - يزيل أحرف Null bytes والرموز الخاصة.
    - يتحقق من الأسماء المحجوزة في نظام الملفات.
    - يُنشئ بادئة فريدة UUID4 تمنع التصادم والتخمين.
    """
    if not original_filename:
        original_filename = "document.pdf"

    # 1. إزالة مسارات المجلدات ومحركات الأقراص
    base_name = os.path.basename(original_filename.replace('\\', '/'))
    # إزالة Null bytes
    base_name = base_name.replace('\x00', '').strip()

    # 2. استخراج الامتداد
    parts = base_name.rsplit('.', 1)
    if len(parts) == 2:
        name_part, ext_part = parts[0], '.' + parts[1].lower()
    else:
        name_part, ext_part = base_name, '.pdf'

    # التحقق من أن الامتداد مسموح به
    if ext_part not in config.ALLOWED_EXTENSIONS:
        ext_part = '.pdf'

    # تنظيف اسم الملف الأساسي من الرموز غير الآمنة
    clean_name = re.sub(r'[^\w\s\u0600-\u06FF\.\-_]', '', name_part).strip()
    if not clean_name or clean_name.upper() in _RESERVED_NAMES:
        clean_name = "file"

    # اقتصار الطول لتفادي قيود نظام التشغيل
    clean_name = clean_name[:60]
    unique_prefix = uuid.uuid4().hex[:12]

    return f"{unique_prefix}_{clean_name}{ext_part}"


def check_file_duplicate_in_repository(
    file_hash: str,
    current_user: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    فحص ما إذا كانت البصمة الرقمية للملف موجودة مسبقاً في الأبحاث السابقة.
    يُطبق قواعد الخصوصية وحماية البيانات:
    - إذا كان للمستخدم صلاحية الاطلاع: يُعاد الرقم المرجعي ومعلومات التقرير ونسبة الاستلال.
    - إذا لم تكن له صلاحية: تُعاد رسالة عامة دون كشف اسم الباحث أو العنوان أو النسبة.
    """
    if not file_hash:
        return None

    existing = batch_repo.get_research_by_file_hash(file_hash)
    if not existing:
        return None

    # التحقق من صلاحية وصول المستخدم للبحث السابق
    is_authorized = True
    if current_user:
        # فحص إمكانية الاطلاع
        user_has_perm = has_permission(current_user, Permission.RESEARCH_VIEW) or has_permission(current_user, Permission.REPORT_VIEW)
        can_access = can_view_research(current_user, existing)
        is_authorized = user_has_perm and can_access

    hash_prefix = file_hash[:16]

    if is_authorized:
        rep = existing.get('report') or {}
        return {
            'duplicate': True,
            'scope': 'existing_research',
            'can_view_existing': True,
            'can_rescan': True,
            'message': 'سبق رفع هذا الملف وفحصه في المنظومة.',
            'existing_research_id': existing.get('research_id'),
            'existing_research_reference': existing.get('reference_number', ''),
            'existing_report_id': existing.get('report_id') or rep.get('report_id'),
            'existing_scan_date': rep.get('scan_date') or existing.get('created_at'),
            'existing_similarity_pct': rep.get('overall_pct'),
            'existing_title': existing.get('title'),
            'existing_author': existing.get('author'),
            'file_hash_prefix': hash_prefix
        }
    else:
        # رد محمي الخصوصية لا يسرب بيانات الباحث أو البحث
        return {
            'duplicate': True,
            'scope': 'existing_research',
            'can_view_existing': False,
            'can_rescan': True,
            'message': 'تم اكتشاف ملف مطابق لملف موجود مسبقاً في المنظومة.',
            'file_hash_prefix': hash_prefix
        }


def verify_stored_file_integrity(file_path: str, expected_hash: str) -> Tuple[bool, str, int]:
    """
    فحص السلامة والمطابقة للملف المخزن على الخادم:
    - يعيد حساب SHA-256 من القرص ويقارنه مع البصمة المسجلة في قاعدة البيانات.
    - إذا حدث اختلاف، يوثق حدث file.integrity_check_failed في سجل التدقيق.
    يُعيد (is_valid, computed_hash, file_size_bytes).
    """
    if not os.path.exists(file_path):
        audit_service.record_event(
            action="file.integrity_check_failed",
            category="system",
            success=False,
            failure_reason_code="FILE_NOT_FOUND",
            metadata={"expected_hash_prefix": expected_hash[:16] if expected_hash else ""}
        )
        return False, "", 0

    computed_hash, size_bytes = compute_stream_sha256(file_path)
    is_valid = (computed_hash.lower() == expected_hash.lower())

    if not is_valid:
        audit_service.record_event(
            action="file.integrity_check_failed",
            category="system",
            success=False,
            failure_reason_code="HASH_MISMATCH",
            metadata={
                "expected_hash_prefix": expected_hash[:16] if expected_hash else "",
                "computed_hash_prefix": computed_hash[:16],
                "size_bytes": size_bytes
            }
        )

    return is_valid, computed_hash, size_bytes
