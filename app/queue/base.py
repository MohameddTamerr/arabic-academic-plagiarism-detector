# -*- coding: utf-8 -*-
"""
الواجهات المعيارية لطابور المهام والأقفال الموزعة (Job Queue & Distributed Lock Abstractions):
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class JobQueueBackend(ABC):
    """الواجهة القياسية الموحدة لطابور المهام الموزع."""

    @abstractmethod
    def enqueue(
        self,
        job_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 3,
        research_id: Optional[int] = None,
        batch_id: Optional[str] = None,
        department_id: Optional[str] = None,
        delay_seconds: int = 0
    ) -> str:
        """إدراج مهمة جديدة في الطابور الدائم وإرجاع معرفها."""
        pass

    @abstractmethod
    def claim(
        self,
        worker_id: str,
        capabilities: List[str],
        lease_seconds: int = 60,
        max_jobs: int = 1
    ) -> List[Dict[str, Any]]:
        """الاستحواذ الذري على مهام جاهزة ومطابقة لإمكانيات العامل."""
        pass

    @abstractmethod
    def heartbeat(self, job_id: str, claim_token: str, extend_seconds: int = 60) -> bool:
        """إرسال نبضة حياة لتمديد عقد إيجار المهمة الجارية."""
        pass

    @abstractmethod
    def complete(self, job_id: str, claim_token: str, result_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """اعتماد اكتمال المهمة بنجاح وتحريرها."""
        pass

    @abstractmethod
    def fail(
        self,
        job_id: str,
        claim_token: str,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        backoff_seconds: int = 10
    ) -> bool:
        """تسجيل فشل المهمة وتحديد إمكانية إعادة المحاولة."""
        pass

    @abstractmethod
    def cancel(self, job_id: str, reason: str = "Admin requested") -> bool:
        """إلغاء مهمة محددة بأمر إداري معتمد."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات وتفاصيل مهمة محددة."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """استرجاع إحصائيات عمق الطابور وحالات المهام."""
        pass

    @abstractmethod
    def recover_stale_jobs(self, timeout_seconds: int = 60) -> int:
        """استعادة المهام المنتهية عقود إيجارها بسبب انهيار العمال."""
        pass


class DistributedLockBackend(ABC):
    """الواجهة القياسية للأقفال الموزعة."""

    @abstractmethod
    def acquire(self, lock_name: str, owner_token: str, ttl_seconds: int = 120) -> bool:
        """محاولة الاستحواذ على قفل موزع محدد."""
        pass

    @abstractmethod
    def release(self, lock_name: str, owner_token: str) -> bool:
        """تحرير قفل موزع مستحوذ عليه."""
        pass

    @abstractmethod
    def is_locked(self, lock_name: str) -> bool:
        """فحص حالة القفل الموزع."""
        pass
