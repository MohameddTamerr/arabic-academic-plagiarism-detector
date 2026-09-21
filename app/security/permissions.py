# -*- coding: utf-8 -*-
"""
الوحدة المركزية لتعريف الصلاحيات والأدوار المؤسسية (RBAC System Core):
- قائمة الصلاحيات المعيارية (Machine-Readable Permissions).
- قائمة الأدوار المؤسسية ومصفوفة الصلاحيات الافتراضية (Default Permission Matrix).
- دوال المواءمة والترقية للأدوار السابقة (Legacy Role Migration).
- استخراج والتحقق من الصلاحيات الصريحة.
"""

from enum import Enum
from typing import Set, Dict, Optional, Any, List


class Permission:
    # 1. إدارة واستعراض الأبحاث (Research)
    RESEARCH_UPLOAD = "research.upload"
    RESEARCH_VIEW = "research.view"
    RESEARCH_EDIT_METADATA = "research.edit_metadata"

    # 2. الفحص وإعادة المحاولة (Scanning)
    SCAN_START = "scan.start"
    SCAN_RETRY = "scan.retry"

    # 3. إدارة الدفعات (Batches)
    BATCH_CREATE = "batch.create"
    BATCH_VIEW = "batch.view"
    BATCH_RETRY = "batch.retry"

    # 4. التقارير والتصدير والاعتماد (Reports & Integrity)
    REPORT_VIEW = "report.view"
    REPORT_EXPORT = "report.export"
    REPORT_FINALIZE = "report.finalize"
    REPORT_VOID = "report.void"

    # 5. المسار والتحكيم الأكاديمي (Academic Review)
    REVIEW_VIEW = "review.view"
    REVIEW_PRELIMINARY = "review.preliminary"
    REVIEW_REJECT = "review.reject"
    REVIEW_FINAL = "review.final"

    # 6. قاعدة المراجع المعتمدة وحوكمتها (Reference Papers & Corpus Governance)
    REFERENCE_VIEW = "reference.view"
    REFERENCE_ADD = "reference.add"
    REFERENCE_METADATA_EDIT = "reference.metadata.edit"
    REFERENCE_RETIRE = "reference.retire"
    REFERENCE_SUPERSEDE = "reference.supersede"
    REFERENCE_REACTIVATE = "reference.reactivate"
    REFERENCE_INTEGRITY_VERIFY = "reference.integrity.verify"
    REFERENCE_CORPUS_MANAGE = "reference.corpus.manage"
    REFERENCE_MANAGE = "reference.manage"

    # 7. إدارة المستخدمين واسترداد الحسابات (Users & Account Recovery)
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    USER_RECOVERY_VIEW_STATUS = "users.recovery.view_status"
    USER_RECOVERY_REVOKE = "users.recovery.revoke"
    USER_PASSWORD_ADMIN_RESET = "users.password.admin_reset"

    # 8. إعدادات المنظومة (Settings)
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"

    # 9. سجل التدقيق والمراجعة (Audit Trail)
    AUDIT_VIEW = "audit.view"

    # 10. النسخ الاحتياطي والاستعادة (Backup & Restore)
    BACKUP_CREATE = "backup.create"
    BACKUP_RESTORE = "backup.restore"

    # 11. تشخيص وصيانة المنظومة (System Health & Maintenance)
    SYSTEM_HEALTH_VIEW = "system.health.view"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # 12. إدارة ومراقبة طابور المهام (Job Management & Queue Operations)
    JOB_VIEW = "job.view"
    JOB_VIEW_ALL = "job.view_all"
    JOB_CANCEL = "job.cancel"
    JOB_RETRY = "job.retry"
    JOB_MANAGE = "job.manage"

    # 13. إدارة الرسائل متعددة الأجزاء (Thesis & Multi-Part Management)
    THESIS_VIEW = "thesis.view"
    THESIS_CREATE = "thesis.create"
    THESIS_EDIT = "thesis.edit"
    THESIS_ADD_PART = "thesis.add_part"
    THESIS_REMOVE_PART = "thesis.remove_part"
    THESIS_SCAN = "thesis.scan"
    THESIS_REPORT_VIEW = "thesis.report.view"
    THESIS_REPORT_FINALIZE = "thesis.report.finalize"


class Role:
    EMPLOYEE = "employee"               # موظف فحص وتشغيل (عمليات فقط)
    DATA_ENTRY = "data_entry"           # مدخل بيانات
    REVIEWER = "reviewer"               # مراجع أكاديمي
    SENIOR_REVIEWER = "senior_reviewer" # مراجع أول / مراجع نهائي
    UNIT_MANAGER = "unit_manager"       # مسؤول وحدة
    SYSTEM_ADMIN = "system_admin"       # مدير النظام

    # أدوار قديمة للتوافق الرجعي
    LEGACY_ADMIN = "admin"
    LEGACY_EMPLOYEE = "employee"


# التسميات المؤسسية باللغة العربية
ROLE_LABELS_AR: Dict[str, str] = {
    Role.EMPLOYEE: "موظف فحص",
    Role.DATA_ENTRY: "مدخل بيانات",
    Role.REVIEWER: "مراجع أكاديمي",
    Role.SENIOR_REVIEWER: "مراجع أول / مراجع نهائي",
    Role.UNIT_MANAGER: "مسؤول وحدة الفحص",
    Role.SYSTEM_ADMIN: "مدير النظام التقني",
    Role.LEGACY_ADMIN: "مدير النظام (حساب عام)",
}


# خريطة مصفوفة الصلاحيات الافتراضية لكل دور (Default Role-Permission Matrix)
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Role.EMPLOYEE: {
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_START,
        Permission.SCAN_RETRY,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.BATCH_RETRY,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REFERENCE_VIEW,
        Permission.JOB_VIEW,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
    },
    Role.DATA_ENTRY: {
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_START,
        Permission.SCAN_RETRY,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.BATCH_RETRY,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REFERENCE_VIEW,
        Permission.JOB_VIEW,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
    },
    Role.REVIEWER: {
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_START,
        Permission.SCAN_RETRY,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.BATCH_RETRY,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REFERENCE_VIEW,
        Permission.REVIEW_VIEW,
        Permission.REVIEW_PRELIMINARY,
        Permission.REVIEW_REJECT,
        Permission.JOB_VIEW,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
    },
    Role.SENIOR_REVIEWER: {
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_START,
        Permission.SCAN_RETRY,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.BATCH_RETRY,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REPORT_FINALIZE,
        Permission.REFERENCE_VIEW,
        Permission.REVIEW_VIEW,
        Permission.REVIEW_PRELIMINARY,
        Permission.REVIEW_REJECT,
        Permission.REVIEW_FINAL,
        Permission.JOB_VIEW,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
        Permission.THESIS_REPORT_FINALIZE,
    },
    Role.UNIT_MANAGER: {
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_START,
        Permission.SCAN_RETRY,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.BATCH_RETRY,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REFERENCE_VIEW,
        Permission.REFERENCE_ADD,
        Permission.REFERENCE_METADATA_EDIT,
        Permission.REFERENCE_RETIRE,
        Permission.REFERENCE_SUPERSEDE,
        Permission.REFERENCE_REACTIVATE,
        Permission.REFERENCE_INTEGRITY_VERIFY,
        Permission.REFERENCE_CORPUS_MANAGE,
        Permission.REFERENCE_MANAGE,
        Permission.SYSTEM_HEALTH_VIEW,
        Permission.JOB_VIEW,
        Permission.JOB_VIEW_ALL,
        Permission.JOB_CANCEL,
        Permission.JOB_RETRY,
        Permission.JOB_MANAGE,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
    },
    Role.SYSTEM_ADMIN: {
        Permission.REVIEW_PRELIMINARY,
        Permission.REVIEW_REJECT,
        Permission.REVIEW_FINAL,
        Permission.RESEARCH_EDIT_METADATA,
        Permission.SCAN_RETRY,
        Permission.BATCH_RETRY,
        Permission.THESIS_REPORT_FINALIZE,
        Permission.SCAN_START,
        Permission.RESEARCH_UPLOAD,
        Permission.RESEARCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.BATCH_VIEW,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.REPORT_FINALIZE,
        Permission.REPORT_VOID,
        Permission.REVIEW_VIEW,
        Permission.REFERENCE_VIEW,
        Permission.REFERENCE_ADD,
        Permission.REFERENCE_METADATA_EDIT,
        Permission.REFERENCE_RETIRE,
        Permission.REFERENCE_SUPERSEDE,
        Permission.REFERENCE_REACTIVATE,
        Permission.REFERENCE_INTEGRITY_VERIFY,
        Permission.REFERENCE_CORPUS_MANAGE,
        Permission.REFERENCE_MANAGE,
        Permission.USERS_VIEW,
        Permission.USERS_MANAGE,
        Permission.USER_RECOVERY_VIEW_STATUS,
        Permission.USER_RECOVERY_REVOKE,
        Permission.USER_PASSWORD_ADMIN_RESET,
        Permission.SETTINGS_VIEW,
        Permission.SETTINGS_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.BACKUP_CREATE,
        Permission.BACKUP_RESTORE,
        Permission.SYSTEM_HEALTH_VIEW,
        Permission.SYSTEM_MAINTENANCE,
        Permission.JOB_VIEW,
        Permission.JOB_VIEW_ALL,
        Permission.JOB_CANCEL,
        Permission.JOB_RETRY,
        Permission.JOB_MANAGE,
        Permission.THESIS_VIEW,
        Permission.THESIS_CREATE,
        Permission.THESIS_EDIT,
        Permission.THESIS_ADD_PART,
        Permission.THESIS_REMOVE_PART,
        Permission.THESIS_SCAN,
        Permission.THESIS_REPORT_VIEW,
    },
}

# مواءمة الأدوار القديمة:
ROLE_PERMISSIONS[Role.LEGACY_ADMIN] = set(ROLE_PERMISSIONS[Role.SYSTEM_ADMIN]) | {
    Permission.RESEARCH_UPLOAD,
    Permission.SCAN_START,
    Permission.BATCH_CREATE,
    Permission.REPORT_EXPORT
}


def normalize_role(raw_role: Optional[str]) -> str:
    """
    تحويل وتوحيد مسمى الدور ليتطابق مع أدوار المنظومة المعتمدة.
    """
    if not raw_role:
        return Role.EMPLOYEE
    clean = str(raw_role).strip().lower()
    if clean in (Role.SYSTEM_ADMIN, 'system_admin', 'sysadmin', 'مدير النظام', 'مدير النظام التقني'):
        return Role.SYSTEM_ADMIN
    if clean in (Role.LEGACY_ADMIN, 'admin', 'administrator', 'مدير'):
        return Role.LEGACY_ADMIN
    if clean in (Role.SENIOR_REVIEWER, 'senior_reviewer', 'senior', 'مراجع أول', 'مراجع نهائي'):
        return Role.SENIOR_REVIEWER
    if clean in (Role.UNIT_MANAGER, 'unit_manager', 'manager', 'مسؤول وحدة', 'مسؤول وحدة الفحص'):
        return Role.UNIT_MANAGER
    if clean in (Role.REVIEWER, 'reviewer', 'مراجع', 'مراجع أكاديمي'):
        return Role.REVIEWER
    if clean in (Role.EMPLOYEE, 'employee', 'موظف', 'موظف فحص'):
        return Role.EMPLOYEE
    if clean in (Role.DATA_ENTRY, 'data_entry', 'entry', 'مدخل بيانات'):
        return Role.DATA_ENTRY
    return clean


def get_role_permissions(role: Role) -> Set[Permission]:
    """Return all permissions granted to a role."""
    return ROLE_PERMISSIONS.get(role, set())


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Check if a given Role enum has a specific Permission."""
    return permission in get_role_permissions(role)


def has_permission(role_str: str, permission_str: str) -> bool:
    """Check if a string role has a given permission."""
    try:
        role = normalize_role(role_str)
        return role_has_permission(role, permission_str)
    except Exception:
        return False


def get_user_permissions(user_dict_or_obj: Any) -> List[str]:
    """استرجاع قائمة الصلاحيات لمستخدم كـ list مرتبة."""
    if not user_dict_or_obj:
        return []
    role = ''
    if isinstance(user_dict_or_obj, dict):
        role = user_dict_or_obj.get('role', '')
    else:
        role = getattr(user_dict_or_obj, 'role', '')
    return sorted(list(get_role_permissions(normalize_role(role))))
