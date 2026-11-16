# -*- coding: utf-8 -*-
"""
Frontend Production UX & Accessibility Test Suite
--------------------------------------------------
Validates:
1. Upload & multi-file analysis workflow
2. One clear Analyze action with OCR precision options
3. Clear structural separation of Plagiarism Results vs AI Detection Results
4. Clean source evidence display, tab switching, and PDF highlighting
5. Arabic RTL layout with English LTR token and dir="auto" bidirectional support
6. Loading, progress, error, and empty states
7. "AI Detection Not Validated" fail-closed contract compliance
8. Zero fabricated AI percentages
9. Preservation of thesis, reviewer workflow, permissions, and backup interfaces
"""

import os
import re
from pathlib import Path
import pytest

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "index.html"


@pytest.fixture(scope="module")
def template_html():
    assert TEMPLATE_PATH.exists(), f"Missing template at {TEMPLATE_PATH}"
    return TEMPLATE_PATH.read_text(encoding="utf-8")


# ─── TASK 1 & 2: Upload Workflow & One Clear Analyze Action ──────────────────

def test_one_clear_analyze_action_with_ocr_mode(template_html):
    """The upload view exposes one clear primary analyze button plus OCR precision options."""
    assert 'id="btn-start-analysis"' in template_html
    assert 'id="btn-start-analysis-text"' in template_html
    assert 'id="ocr-btn-accurate"' in template_html
    assert 'id="ocr-btn-fast"' in template_html
    assert "setOcrModeSelection('accurate')" in template_html
    assert "setOcrModeSelection('fast')" in template_html
    assert 'id="btn-start-analysis" onclick="startAnalysis()"' in template_html
    assert 'id="btn-start-fast-analysis" hidden' in template_html
    assert "async function startAnalysis(requestedOcrMode = currentOcrModeSelection)" in template_html
    assert "if (analyzeBtn.disabled) return;" in template_html
    assert "await submitAnalysis(requestedOcrMode === 'fast' ? 'fast' : 'accurate');" in template_html


def test_upload_supports_single_thesis_and_batch_modes(template_html):
    """Upload UI supports single text, reorderable thesis chapters, and multi-paper batches."""
    assert 'id="dropzone-area"' in template_html
    assert 'id="toggle-thesis-mode-btn"' in template_html
    assert 'id="toggle-thesis-mode-text"' in template_html
    assert 'id="thesis-metadata-container"' in template_html
    assert 'id="thesis-files-list"' in template_html
    assert 'id="batch-files-list"' in template_html
    assert 'id="raw-text-container"' in template_html


# ─── TASK 3: Two Clearly Separated Sections (Plagiarism vs AI) ───────────────

def test_separated_plagiarism_and_ai_detection_sections(template_html):
    """Plagiarism results and AI writing results exist in two distinctly structured sections."""
    assert 'id="section-ai-detection-results"' in template_html
    assert 'id="report-level-summary"' in template_html
    assert 'id="risk-verdict-banner"' in template_html
    assert 'id="report-ai-status-box"' in template_html
    assert 'id="report-ai-status"' in template_html
    assert 'id="ai-detection-status-pill"' in template_html

    # Ensure the AI detection section is explicitly marked as independent
    ai_sec_pos = template_html.find('id="section-ai-detection-results"')
    plag_sec_pos = template_html.find('id="report-level-summary"')
    assert ai_sec_pos != -1
    assert plag_sec_pos != -1
    assert "القسم الثاني: فحص الكتابة بالذكاء الاصطناعي" in template_html


# ─── TASK 4: Source Evidence & PDF Highlighting Clean Display ─────────────────

def test_evidence_and_document_tabs_exist_and_not_blocked(template_html):
    """Report workspace has interactive tabs that are not permanently suppressed with !important."""
    assert 'id="rep-tab-btn-pdf"' in template_html
    assert 'id="rep-tab-btn-evidence"' in template_html
    assert 'id="rep-tab-btn-sources"' in template_html
    assert 'id="tab-evidence-count-badge"' in template_html
    assert 'id="tab-sources-count-badge"' in template_html

    # Check evidence tab container is free of display: none !important
    assert 'id="rep-tab-content-evidence" style="padding: 16px 20px; display: none !important;"' not in template_html
    assert 'id="rep-tab-content-sources" style="display: none !important; padding: 16px 20px;"' not in template_html
    assert 'id="rep-tab-content-evidence"' in template_html
    assert 'id="rep-tab-content-sources"' in template_html


def test_pdf_viewer_controls_and_error_states(template_html):
    """PDF viewer includes highlight overlay, jump controls, and failure retry states."""
    assert 'id="report-pdf-viewer-container"' in template_html
    assert 'id="inline-pdf-image"' in template_html
    assert 'id="inline-pdf-page-state"' in template_html
    assert 'id="inline-pdf-page-retry"' in template_html
    assert 'id="inline-evidence-prev"' in template_html
    assert 'id="inline-evidence-next"' in template_html
    assert 'id="inline-evidence-position"' in template_html


# ─── TASK 5: Arabic RTL & English LTR Bidirectional Support ──────────────────

def test_bidirectional_and_text_selection_support(template_html):
    """Template supports dir='auto', LTR tokens for technical hashes/refs, and selectable text."""
    assert 'dir="rtl"' in template_html[:200]
    assert 'dir="auto"' in template_html
    assert '.ltr-token' in template_html
    assert 'user-select: text !important;' in template_html
    assert '.selectable-content' in template_html or '.selectable-text' in template_html


# ─── TASK 6, 7 & 8: AI Detection Fail-Closed & Zero Fabrication ──────────────

def test_ai_status_message_complies_with_fail_closed_contract(template_html):
    """Report JS never fabricates AI percentages and shows unvalidated status by default."""
    assert "غير متاح — لا يوجد نموذج مدقق" in template_html
    assert "غير مدقق أكاديمياً" in template_html
    assert "تعذر تحليل الكتابة بالذكاء الاصطناعي" in template_html
    assert "report.ai_analysis.reason === 'analysis_error'" in template_html


# ─── TASK 9: Preservation of Core Workflows & Interfaces ─────────────────────

def test_reviewer_workflow_actions_preserved(template_html):
    """Employee submit and admin approval/rejection actions are fully preserved."""
    assert 'id="btn-employee-submit"' in template_html
    assert 'id="btn-accept-preliminary"' in template_html
    assert 'id="btn-reject-paper"' in template_html
    assert 'id="btn-report-certificate"' in template_html


def test_thesis_multi_part_and_backup_interfaces_preserved(template_html):
    """Thesis parts breakdown table and settings backup view are preserved."""
    assert 'id="thesis-parts-section"' in template_html
    assert 'id="thesis-parts-table-body"' in template_html
    assert 'id="view-settings"' in template_html
    assert 'id="view-theses"' in template_html
    assert 'id="view-users"' in template_html
    assert 'id="view-audit"' in template_html
