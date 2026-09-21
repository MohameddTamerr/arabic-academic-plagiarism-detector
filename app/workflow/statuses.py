# -*- coding: utf-8 -*-
"""
التعريفات المركزية لحالات الفحص التقني والتحكيم الأكاديمي (Workflow Status Model):
- الفصل التام بين الحالة التقنية للفحص (Scan Status) والحالة الإجرائية للتحكيم (Review Status).
- ضبط وتوثيق الانتقالات المسموحة برمجياً (State Machine Transitions).
- توفير دوال المواءمة مع الحالات التاريخية (Legacy Status Mapping).
"""

from enum import Enum
from typing import Optional, Tuple, Set


class ScanStatus(str, Enum):
    """حالات معالجة الفحص التقني للمستند."""
    QUEUED = "queued"             # في طابور الفحص
    PROCESSING = "processing"     # جاري المعالجة والتحليل
    COMPLETED = "completed"       # مكتمل الفحص التقني بنجاح
    FAILED = "failed"             # تعذر الفحص (خطأ استخراج أو معالجة)
    INTERRUPTED = "interrupted"   # انقطع الفحص (إعادة تشغيل الخادم أثناء العمل)


class ReviewStatus(str, Enum):
    """حالات المسار الأكاديمي والتحكيم والاعتماد."""
    PENDING_REVIEW = "pending_review"                 # قيد الفحص والمراجعة الأكاديمية
    PRELIMINARY_ACCEPTED = "preliminary_accepted"     # قبول مبدئي
    REJECTED = "rejected"                             # مرفوض أكاديمياً
    FINAL_ACCEPTED = "final_accepted"                 # اعتماد نهائي


# ─── التسميات العربية المؤسسية المعتمدة ─────────────────────────────────────

SCAN_STATUS_LABELS_AR = {
    ScanStatus.QUEUED.value: "في الانتظار",
    ScanStatus.PROCESSING.value: "جاري المعالجة",
    ScanStatus.COMPLETED.value: "مكتمل الفحص",
    ScanStatus.FAILED.value: "تعذر الفحص",
    ScanStatus.INTERRUPTED.value: "منقطع",
}

REVIEW_STATUS_LABELS_AR = {
    ReviewStatus.PENDING_REVIEW.value: "قيد المراجعة",
    ReviewStatus.PRELIMINARY_ACCEPTED.value: "قبول مبدئي",
    ReviewStatus.REJECTED.value: "مرفوض",
    ReviewStatus.FINAL_ACCEPTED.value: "اعتماد نهائي",
}


# ─── مصفوفة الانتقالات المسموحة (State Machine) ──────────────────────────────

VALID_SCAN_TRANSITIONS: dict[str, Set[str]] = {
    ScanStatus.QUEUED.value: {
        ScanStatus.PROCESSING.value,
        ScanStatus.FAILED.value,
        ScanStatus.INTERRUPTED.value
    },
    ScanStatus.PROCESSING.value: {
        ScanStatus.COMPLETED.value,
        ScanStatus.FAILED.value,
        ScanStatus.INTERRUPTED.value
    },
    ScanStatus.COMPLETED.value: {
        ScanStatus.QUEUED.value,
        ScanStatus.PROCESSING.value  # إعادة الفحص (Rescan)
    },
    ScanStatus.FAILED.value: {
        ScanStatus.QUEUED.value,
        ScanStatus.PROCESSING.value  # إعادة المحاولة (Retry)
    },
    ScanStatus.INTERRUPTED.value: {
        ScanStatus.QUEUED.value,
        ScanStatus.PROCESSING.value  # استئناف/إعادة المحاولة
    }
}

VALID_REVIEW_TRANSITIONS: dict[str, Set[str]] = {
    ReviewStatus.PENDING_REVIEW.value: {
        ReviewStatus.FINAL_ACCEPTED.value,
        ReviewStatus.PRELIMINARY_ACCEPTED.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.PENDING_REVIEW.value  # إعادة إرسال بملاحظات
    },
    ReviewStatus.PRELIMINARY_ACCEPTED.value: {
        ReviewStatus.FINAL_ACCEPTED.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.PRELIMINARY_ACCEPTED.value
    },
    ReviewStatus.REJECTED.value: {
        ReviewStatus.PENDING_REVIEW.value,      # التماس / إعادة مراجعة
        ReviewStatus.PRELIMINARY_ACCEPTED.value
    },
    ReviewStatus.FINAL_ACCEPTED.value: set()     # حالة نهائية معتمدة
}


VALID_SCAN_STATUSES = {s.value for s in ScanStatus}


def validate_scan_transition(current_status: Optional[str], target_status: str) -> bool:
    """التحقق من صحة وقانونية الانتقال التقني للفحص."""
    target = str(target_status).strip().lower() if target_status else ''
    if target not in VALID_SCAN_STATUSES:
        return False
    if not current_status:
        return True  # إنشاء أولي لحالة قانونية
    current = str(current_status).strip().lower()
    if current not in VALID_SCAN_STATUSES:
        return False
    if current == target:
        return True
    allowed = VALID_SCAN_TRANSITIONS.get(current, set())
    return target in allowed


def validate_review_transition(current_status: Optional[str], target_status: str) -> bool:
    """التحقق من صحة وقانونية الانتقال الإجرائي للتحكيم الأكاديمي."""
    if not current_status:
        return True
    current = str(current_status).strip().lower()
    target = str(target_status).strip().lower()
    if current == target:
        return True
    allowed = VALID_REVIEW_TRANSITIONS.get(current, set())
    return target in allowed


# ─── دوال التوافق والمواءمة مع الحالات التاريخية (Legacy Mapping) ────────────

def map_legacy_status(old_status: Optional[str]) -> Tuple[str, str]:
    """
    تحويل الحالات القديمة المختلطة إلى النموذجين الصريحين:
    (scan_status, review_status)
    """
    if not old_status:
        return ScanStatus.COMPLETED.value, ReviewStatus.PENDING_REVIEW.value

    s = str(old_status).strip().lower()

    if s in ('مفحوص', 'محفوظ', 'completed', 'مكتمل'):
        return ScanStatus.COMPLETED.value, ReviewStatus.PENDING_REVIEW.value
    elif s in ('قيد المراجعة', 'pending_review', 'submitted'):
        return ScanStatus.COMPLETED.value, ReviewStatus.PENDING_REVIEW.value
    elif s in ('قبول مبدئي', 'preliminary_accepted', 'initial_accepted'):
        return ScanStatus.COMPLETED.value, ReviewStatus.PRELIMINARY_ACCEPTED.value
    elif s in ('مرفوض', 'rejected'):
        return ScanStatus.COMPLETED.value, ReviewStatus.REJECTED.value
    elif s in ('قبول نهائي', 'final_accepted', 'approved'):
        return ScanStatus.COMPLETED.value, ReviewStatus.FINAL_ACCEPTED.value
    elif s in ('running', 'processing', 'جاري الفحص', 'جاري المعالجة'):
        return ScanStatus.PROCESSING.value, ReviewStatus.PENDING_REVIEW.value
    elif s in ('queued', 'pending', 'في الانتظار'):
        return ScanStatus.QUEUED.value, ReviewStatus.PENDING_REVIEW.value
    elif s in ('error', 'failed', 'خطأ'):
        return ScanStatus.FAILED.value, ReviewStatus.PENDING_REVIEW.value
    elif s in ('interrupted', 'منقطع'):
        return ScanStatus.INTERRUPTED.value, ReviewStatus.PENDING_REVIEW.value

    # الحالة الافتراضية الآمنة
    return ScanStatus.COMPLETED.value, ReviewStatus.PENDING_REVIEW.value


def derive_legacy_status(scan_status: str, review_status: str) -> str:
    """
    اشتقاق حقل status القديم لضمان التوافق مع أي واجهات برمجية سابقة (Compatibility-Only).
    """
    if scan_status == ScanStatus.FAILED.value:
        return "error"
    elif scan_status == ScanStatus.INTERRUPTED.value:
        return "interrupted"
    elif scan_status == ScanStatus.PROCESSING.value:
        return "running"
    elif scan_status == ScanStatus.QUEUED.value:
        return "queued"

    # إذا كان الفحص مكتملاً، فالحالة المشتقة تعكس حالة التحكيم
    if review_status == ReviewStatus.PRELIMINARY_ACCEPTED.value:
        return "قبول مبدئي"
    elif review_status == ReviewStatus.REJECTED.value:
        return "مرفوض"
    elif review_status == ReviewStatus.FINAL_ACCEPTED.value:
        return "قبول نهائي"
    elif review_status == ReviewStatus.PENDING_REVIEW.value:
        return "مفحوص"

    return "مفحوص"
