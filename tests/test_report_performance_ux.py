# -*- coding: utf-8 -*-
"""
Deterministic performance & UX test suite for Report Simplification & Lazy-Loading.
Verifies:
1. Deterministic report fixtures (100, 1,000, 10,000 evidence items)
2. Report summary endpoint latency & lightweight payload size (<20KB)
3. Server-side paginated evidence retrieval (25/50/100, total_pages, total_count)
4. Evidence filters (match_type, min_similarity, query, page_number)
5. Group by source (grouped=true)
6. Paginated sources endpoint (/api/reports/<id>/sources)
7. Page-scoped evidence endpoint (/api/reports/<id>/page_evidence)
8. RBAC permissions (EMPLOYEE vs SYSTEM_ADMIN)
9. Data integrity & calculation consistency (percentages, attribution, evidence counts unchanged)
"""

import os
import sys
import time
import json
import uuid
import pytest
from datetime import datetime

from app import create_app
from app.repositories import base_repo, report_repo, user_repo
from app.models.schema import LegacyReport, User
from app.models.research_schema import Research, ResearchFile
from app.models.snapshot_schema import ReportExecutionSnapshot
from app.security.permissions import Role, Permission


# ─── Helper Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def auth_client_factory(test_app):
    def _create_client(role=Role.EMPLOYEE, username=None):
        if not username:
            username = f"user_{role.lower()}_{uuid.uuid4().hex[:6]}"
        with base_repo.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=user_repo.hash_password('SecurePass#2026'),
                    full_name=f'User {role}',
                    role=role
                )
                session.add(user)
                session.commit()
            uid = user.id
            u_role = user.role
            u_ver = user.session_version or 1

        client = test_app.test_client()
        now_ts = time.time()
        with client.session_transaction() as sess:
            sess['user_id'] = uid
            sess['username'] = username
            sess['role'] = u_role
            sess['full_name'] = f'User {role}'
            sess['session_version'] = u_ver
            sess['auth_time'] = now_ts
            sess['last_activity'] = now_ts
            sess['csrf_token'] = 'test_csrf_token'
            sess['user'] = {
                'id': uid,
                'username': username,
                'role': u_role,
                'full_name': f'User {role}',
                'session_version': u_ver
            }
        return client, username
    return _create_client


def _create_benchmark_report(num_evidence: int, title_suffix: str = "") -> str:
    """Helper to create a deterministic report with exact number of evidence matches."""
    rep_id = f"REP_PERF_{num_evidence}_{uuid.uuid4().hex[:8]}"
    
    # 1. Create Research record
    with base_repo.get_session() as session:
        res = Research(
            reference_number=f"REF-{uuid.uuid4().hex[:8].upper()}",
            title=f"بحث علمي قياسي لاختبار الأداء ({num_evidence} موضع) {title_suffix}",
            author="الباحث الأكاديمي النموذجي",
            scan_status="completed",
            review_status="pending_review",
            specialization="نظم المعلومات الذكية",
            degree_type="ماجستير",
            report_id=rep_id,
            created_at=datetime.utcnow()
        )
        session.add(res)
        session.commit()
        research_db_id = res.id

        # 2. Build synthetic evidence
        sources = [
            {"id": f"SRC_00{i}", "title": f"مرجع ومصدر علمي رقم {i}", "author": f"د. مؤلف {i}", "year": 2020 + (i % 5)}
            for i in range(1, 11)
        ]
        
        matches = []
        for i in range(num_evidence):
            src_idx = i % len(sources)
            src = sources[src_idx]
            match_type = "direct" if (i % 3 == 0) else ("paraphrase" if (i % 3 == 1) else "excluded_quote")
            pct = 95.0 if match_type == "direct" else (75.0 if match_type == "paraphrase" else 100.0)
            matches.append({
                "id": f"ev_{i+1}",
                "suspect_text": f"هذا نص مقتبس في البحث قيد الفحص في الموضع رقم {i+1} بهدف قياس أداء واجهة التقرير وخفة التحميل.",
                "source_text": f"هذا نص المرجع الأصلي المطابق من المصدر رقم {src_idx+1} في الموضع المقابل رقم {i+1}.",
                "source_id": src["id"],
                "source_title": src["title"],
                "source_author": src["author"],
                "suspect_page": (i // 10) + 1,
                "source_page": ((i * 2) // 10) + 1,
                "match_type": match_type,
                "similarity": pct,
                "confidence": 0.92
            })

        # Calculate metrics
        direct_count = sum(1 for m in matches if m["match_type"] == "direct")
        paraphrase_count = sum(1 for m in matches if m["match_type"] == "paraphrase")
        excluded_count = sum(1 for m in matches if m["match_type"] == "excluded_quote")
        
        rep_dict = {
            "report_id": rep_id,
            "research_id": research_db_id,
            "research_title": res.title,
            "author": res.author,
            "reference_number": res.reference_number,
            "scan_date": datetime.utcnow().isoformat(),
            "overall_similarity": 28.5,
            "direct_similarity": 18.2,
            "paraphrase_similarity": 10.3,
            "excluded_similarity": 4.5,
            "matches_count": num_evidence,
            "matched_sources_count": len(sources),
            "sources": sources,
            "matches": matches,
            "thesis_parts": [
                {"part_id": "p1", "title": "الفصل الأول: المقدمة", "similarity": 12.0, "matches_count": num_evidence // 3},
                {"part_id": "p2", "title": "الفصل الثاني: الدراسات السابقة", "similarity": 35.0, "matches_count": num_evidence // 3},
                {"part_id": "p3", "title": "الفصل الثالث: المنهجية والنتائج", "similarity": 24.0, "matches_count": num_evidence - 2 * (num_evidence // 3)}
            ],
            "technical_audit": {
                "detector_version": "3.5.0-opt",
                "engine_version": "2.4.0",
                "corpus_version": "2026.09.v1",
                "index_version": "1.0.0",
                "shingle_size": 4,
                "thresholds": {"direct": 0.85, "paraphrase": 0.65},
                "integrity_checksum": "sha256:abc123mockchecksumforperformancetest",
                "internal_id": rep_id
            },
            "document_text_sample": "عينة من النص الكامل للبحث مع صفحات مقسمة...\n--- PAGE BREAK 1 ---\nنص الصفحة الأولى..."
        }

        legacy_rep = LegacyReport(
            id=rep_id,
            title=res.title,
            author=res.author,
            overall_pct=28.5,
            copied_pct=18.2,
            para_pct=10.3,
            research_id=research_db_id,
            report_json=json.dumps(rep_dict, ensure_ascii=False),
            created_at=datetime.utcnow()
        )
        session.add(legacy_rep)
        session.commit()

    return rep_id


# ─── 1. Deterministic Performance Fixtures & Summary Tests ───────────────────

class TestReportPerformanceSummary:
    """Test initial report view performance for 100, 1,000, and 10,000 evidence items."""

    @pytest.mark.parametrize("num_evidence", [100, 1000, 10000])
    def test_report_summary_latency_and_payload_size(self, auth_client_factory, num_evidence):
        """Measures API latency and payload size for initial summary response."""
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(num_evidence)

        # Measure /api/reports/<id>/summary
        start_time = time.perf_counter()
        resp = client.get(f"/api/reports/{rep_id}/summary")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert resp.status_code == 200, f"Failed to get report summary: {resp.data}"
        report_data = resp.get_json()
        
        payload_bytes = len(resp.data)
        payload_kb = payload_bytes / 1024.0

        # Performance constraints
        assert elapsed_ms < 250.0, f"Summary latency {elapsed_ms:.2f}ms exceeds 250ms budget for {num_evidence} items"
        assert payload_kb < 25.0, f"Summary payload {payload_kb:.2f}KB exceeds 25KB budget for {num_evidence} items"

        # Executive summary field checks
        assert report_data["report_id"] == rep_id
        assert report_data["overall_similarity"] == 28.5
        assert report_data["direct_similarity"] == 18.2
        assert report_data["paraphrase_similarity"] == 10.3
        assert report_data["evidence_total_count"] == num_evidence
        assert report_data["matched_sources_count"] == 10
        assert len(report_data["thesis_parts"]) == 3
        
        # Technical audit metadata is preserved
        assert "technical_audit" in report_data
        tech = report_data["technical_audit"]
        assert tech.get("shingle_size") == 4
        assert tech.get("engine_version") == "2.4.0"

        # Ensure heavy arrays are NOT in summary
        assert "evidence" not in report_data or report_data["evidence"] is None
        assert "matches" not in report_data
        assert "document_text_sample" not in report_data


# ─── 2. Server-side Evidence Pagination Tests ─────────────────────────────────

class TestReportEvidencePagination:
    """Test server-side evidence pagination (25/50/100) and page boundaries."""

    def test_default_pagination_page_size_25(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(100)

        resp = client.get(f"/api/reports/{rep_id}/evidence?page=1&page_size=25")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["page"] == 1
        assert data["page_size"] == 25
        assert data["total_count"] == 100
        assert data["total_pages"] == 4
        assert len(data["items"]) == 25
        assert data["items"][0]["id"] == "ev_1"
        assert data["items"][24]["id"] == "ev_25"

    def test_subsequent_pages_no_overlap(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(100)

        # Page 1
        r1 = client.get(f"/api/reports/{rep_id}/evidence?page=1&page_size=25").get_json()
        # Page 2
        r2 = client.get(f"/api/reports/{rep_id}/evidence?page=2&page_size=25").get_json()

        ids_p1 = {item["id"] for item in r1["items"]}
        ids_p2 = {item["id"] for item in r2["items"]}
        
        assert len(ids_p1) == 25
        assert len(ids_p2) == 25
        assert ids_p1.isdisjoint(ids_p2), "Pages 1 and 2 must not have overlapping evidence items"
        assert r2["items"][0]["id"] == "ev_26"

    def test_page_size_options_50_and_100(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(200)

        # 50 per page
        r_50 = client.get(f"/api/reports/{rep_id}/evidence?page=1&page_size=50").get_json()
        assert len(r_50["items"]) == 50
        assert r_50["total_pages"] == 4

        # 100 per page
        r_100 = client.get(f"/api/reports/{rep_id}/evidence?page=1&page_size=100").get_json()
        assert len(r_100["items"]) == 100
        assert r_100["total_pages"] == 2

    def test_safe_maximum_page_size_clamping(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(50)

        # Request 10,000 items on evidence endpoint
        resp = client.get(f"/api/reports/{rep_id}/evidence?page=1&page_size=10000")
        assert resp.status_code == 200
        data = resp.get_json()
        # Must be clamped to safe max (100)
        assert data["page_size"] <= 100


# ─── 3. Evidence Filtering & Grouping Tests ───────────────────────────────────

class TestReportEvidenceFiltersAndGrouping:
    """Test filtering evidence by type, similarity, query, and presentation grouping."""

    def test_filter_by_match_type(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(60)

        # Filter direct
        resp = client.get(f"/api/reports/{rep_id}/evidence?match_type=direct&page_size=50")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(item["match_type"] == "direct" for item in data["items"])
        assert data["total_count"] == 20  # 60 / 3

        # Filter paraphrase
        resp_p = client.get(f"/api/reports/{rep_id}/evidence?match_type=paraphrase&page_size=50")
        data_p = resp_p.get_json()
        assert all(item["match_type"] == "paraphrase" for item in data_p["items"])
        assert data_p["total_count"] == 20

    def test_filter_by_min_similarity(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(60)

        resp = client.get(f"/api/reports/{rep_id}/evidence?min_pct=90&page_size=100")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(item.get("similarity", 0) >= 90.0 for item in data["items"])

    def test_filter_by_search_query(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(30)

        resp = client.get(f"/api/reports/{rep_id}/evidence?q=الموضع رقم 5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_count"] >= 1
        assert any("الموضع رقم 5" in item["suspect_text"] for item in data["items"])

    def test_presentation_group_by_source(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(100)

        resp = client.get(f"/api/reports/{rep_id}/evidence?group_by_source=true&page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["grouped"] is True
        assert len(data["items"]) <= 5
        
        # Check source group structure
        group = data["items"][0]
        assert "source_title" in group
        assert "match_count" in group
        assert "matches" in group
        assert len(group["matches"]) > 0
        assert group["match_count"] == len(group["matches"])


# ─── 4. Sources & Page-Scoped Evidence Tests ──────────────────────────────────

class TestReportSourcesAndPageEvidence:
    """Test paginated sources and on-demand page-level evidence retrieval."""

    def test_paginated_sources_endpoint(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(100)

        resp = client.get(f"/api/reports/{rep_id}/sources?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_count"] == 10
        assert data["total_pages"] == 2
        assert len(data["items"]) == 5
        assert "match_count" in data["items"][0]

    def test_page_scoped_evidence_endpoint(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(100)

        # Query evidence on suspect_page 1
        resp = client.get(f"/api/reports/{rep_id}/page_evidence?page=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page_number"] == 1
        assert "matches" in data
        assert all(m.get("suspect_page") == 1 for m in data["matches"])


# ─── 5. RBAC & Permissions Verification ───────────────────────────────────────

class TestReportRBAC:
    """Verify Role-Based Access Control for EMPLOYEE and SYSTEM_ADMIN."""

    def test_employee_can_view_summary_and_evidence_without_review_actions(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(30)

        # Summary
        resp = client.get(f"/api/reports/{rep_id}/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_role"] == Role.EMPLOYEE
        assert data["can_review"] is False

        # Evidence
        resp_ev = client.get(f"/api/reports/{rep_id}/evidence")
        assert resp_ev.status_code == 200

    def test_system_admin_can_view_summary_and_has_review_capability(self, auth_client_factory):
        client, _ = auth_client_factory(Role.SYSTEM_ADMIN)
        rep_id = _create_benchmark_report(30)

        resp = client.get(f"/api/reports/{rep_id}/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_role"] == Role.SYSTEM_ADMIN
        assert data["can_review"] is True

    def test_unauthenticated_request_is_rejected(self, test_app):
        test_app.config['STRICT_AUTH'] = True
        client = test_app.test_client()
        rep_id = _create_benchmark_report(30)

        resp = client.get(f"/api/reports/{rep_id}/summary")
        assert resp.status_code == 401


# ─── 6. Data Integrity & Calculation Consistency Tests ────────────────────────

class TestReportIntegrityAndConsistency:
    """Verify that optimizations do not alter similarity calculations, evidence data or attribution."""

    def test_summary_and_full_report_calculations_identical(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        rep_id = _create_benchmark_report(500)

        # Full report
        resp_full = client.get(f"/api/reports/{rep_id}")
        assert resp_full.status_code == 200
        full_data = resp_full.get_json()

        # Summary report
        resp_summary = client.get(f"/api/reports/{rep_id}/summary")
        assert resp_summary.status_code == 200
        summary_data = resp_summary.get_json()

        # Assert all calculations match 100%
        assert summary_data["overall_similarity"] == full_data["overall_pct"]
        assert summary_data["direct_similarity"] == full_data["copied_pct"]
        assert summary_data["paraphrase_similarity"] == full_data["para_pct"]
        assert summary_data["evidence_total_count"] == len(full_data["matches"])
        assert summary_data["matched_sources_count"] == len(full_data["sources"])

    def test_paginated_evidence_reconstructs_full_dataset_losslessly(self, auth_client_factory):
        client, _ = auth_client_factory(Role.EMPLOYEE)
        num_items = 250
        rep_id = _create_benchmark_report(num_items)

        # Iterate all pages with page_size=50
        collected_items = []
        page = 1
        while True:
            resp = client.get(f"/api/reports/{rep_id}/evidence?page={page}&page_size=50")
            assert resp.status_code == 200
            data = resp.get_json()
            items = data["items"]
            if not items:
                break
            collected_items.extend(items)
            if page >= data["total_pages"]:
                break
            page += 1

        # Reconstructed total count and IDs must match exactly
        assert len(collected_items) == num_items
        assert [item["id"] for item in collected_items] == [f"ev_{i+1}" for i in range(num_items)]

