# -*- coding: utf-8 -*-
"""
اختبارات استقرار وثبات الهيكل البصري والتمرير (UI Shell & Scroll Behavior Regression Tests):
- التحقق من ثبات القائمة الجانبية (Sidebar) وشريط الأدوات العلوي (Topbar).
- التأكد من أن منطقة المحتوى الرئيسية (Main Content) هي الحاوية الأساسية للتمرير الرأسي.
- التأكد من تثبيت زر تسجيل الخروج في أسفل القائمة الجانبية.
- التحقق من دعم أنماط الطباعة (@media print) بدون تشويه أو قص للصفحات.
- التحقق من عدم وجود تضارب في أشرطة التمرير المتداخلة.
"""

import os
import re
import pytest

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'index.html')


@pytest.fixture(scope='module')
def template_content():
    """قراءة محتوى ملف القالب الرئيسي."""
    assert os.path.exists(TEMPLATE_PATH), "ملف index.html غير موجود!"
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def test_topbar_sticky_layout(template_content):
    """التحقق من أن الهيدر العلوي مثبت في أعلى الصفحة عبر sticky positioning."""
    assert '.topbar {' in template_content
    topbar_block = re.search(r'\.topbar\s*\{([^}]+)\}', template_content)
    assert topbar_block is not None
    css = topbar_block.group(1)
    assert 'position: sticky' in css
    assert 'top: 0' in css
    assert 'height: 64px' in css


def test_app_container_layout(template_content):
    """التحقق من أن حاوية التطبيق تتمدد بارتفاع الشاشة وتمنع التمرير الخارجي المزدوج."""
    container_block = re.search(r'\.app-container\s*\{([^}]+)\}', template_content)
    assert container_block is not None
    css = container_block.group(1)
    assert 'display: flex' in css
    assert 'calc(100vh - 64px)' in css
    assert 'overflow: hidden' in css


def test_sidebar_fixed_with_internal_scroll(template_content):
    """التحقق من أن القائمة الجانبية ثابتة مع دعم التمرير الداخلي لعناصر التنقل فقط."""
    sidebar_block = re.search(r'\.sidebar\s*\{([^}]+)\}', template_content)
    assert sidebar_block is not None
    sidebar_css = sidebar_block.group(1)
    assert 'width: 260px' in sidebar_css
    assert 'display: flex' in sidebar_css
    assert 'flex-direction: column' in sidebar_css

    sidebar_nav_block = re.search(r'\.sidebar-nav\s*\{([^}]+)\}', template_content)
    assert sidebar_nav_block is not None
    nav_css = sidebar_nav_block.group(1)
    assert 'overflow-y: auto' in nav_css
    assert 'overflow-x: hidden' in nav_css


def test_sidebar_footer_logout_anchoring(template_content):
    """التحقق من تثبيت زر تسجيل الخروج في أسفل القائمة الجانبية."""
    assert 'class="sidebar-footer"' in template_content
    assert 'id="sidebar-logout-btn"' in template_content
    footer_block = re.search(r'\.sidebar-footer\s*\{([^}]+)\}', template_content)
    assert footer_block is not None
    footer_css = footer_block.group(1)
    assert 'flex-shrink: 0' in footer_css
    assert 'margin-top: auto' in footer_css


def test_main_content_primary_scroll(template_content):
    """التحقق من أن منطقة المحتوى الرئيسية هي حاوية التمرير الرأسي الأساسية."""
    main_block = re.search(r'\.main-content\s*\{([^}]+)\}', template_content)
    assert main_block is not None
    main_css = main_block.group(1)
    assert 'flex: 1' in main_css
    assert 'overflow-y: auto' in main_css
    assert 'overflow-x: hidden' in main_css


def test_print_media_rules(template_content):
    """التحقق من وجود قواعد الطباعة وتجاوز قيود التمرير لإتاحة طباعة التقارير كاملة."""
    assert '@media print' in template_content
    # استخراج كتلة @media print
    start_idx = template_content.find('@media print')
    assert start_idx != -1
    # البحث عن محتويات قواعد الطباعة
    print_section = template_content[start_idx:start_idx + 1000]
    assert 'overflow: visible' in print_section
    assert '.topbar' in print_section
    assert '.sidebar' in print_section
    assert '.main-content' in print_section


def test_batch_scan_elapsed_timer_survives_refresh(template_content):
    """عداد الفحص يستند إلى وقت الخادم، ويتوقف عند اكتمال جميع عناصر الدفعة."""
    assert 'id="batch-elapsed-badge"' in template_content
    assert 'id="batch-elapsed-time"' in template_content
    assert 'function parseBatchUtcTimestamp(value)' in template_content
    assert 'function formatBatchElapsed(milliseconds)' in template_content
    assert 'batch.created_at' in template_content
    assert 'item.completed_at' in template_content
    assert 'syncBatchElapsedTimer(batch);' in template_content
    assert 'clearInterval(batchElapsedTimer)' in template_content


def test_authenticated_ui_propagates_csrf_token(template_content):
    """كل طلب يغير الحالة يحمل رمز CSRF الصادر من جلسة الخادم."""
    assert "let csrfToken = '';" in template_content
    assert 'isSameOrigin && isStateChanging && csrfToken' in template_content
    assert "headers.set('X-CSRF-Token', csrfToken);" in template_content
    assert "csrfToken = data.csrf_token || '';" in template_content
    assert "csrfToken = meData.csrf_token || '';" in template_content


def test_saved_browser_user_does_not_replace_server_session(template_content):
    """إعادة تحميل الواجهة تتحقق من جلسة Flask ولا تثق في sessionStorage وحده."""
    assert "const meRes = await fetch('/api/auth/me');" in template_content
    assert 'meData.authenticated && meData.user' in template_content
    assert "sessionStorage.removeItem('police_academy_user');" in template_content


def test_logout_closes_server_session(template_content):
    """تسجيل الخروج يرسل طلباً للخادم قبل تنظيف حالة المتصفح."""
    assert 'async function logoutUser()' in template_content
    assert "await fetch('/api/auth/logout'" in template_content


def test_toast_stays_inside_viewport(template_content):
    """رسائل النجاح والخطأ لا تنزاح خارج الشاشة على أي عرض."""
    assert 'width: min(440px, calc(100vw - 24px));' in template_content
    assert '.toast-container {' in template_content
    assert 'position: fixed;' in template_content
    assert '.custom-toast {' in template_content
    assert "messageElement.className = 'custom-toast-message';" in template_content
    assert '.custom-toast-message {' in template_content
    assert '.toast-container { position:fixed;bottom:24px;left:24px' not in template_content


def test_sidebar_selection_and_report_polling_have_single_active_state(template_content):
    """التنقل المخصص لا يحتفظ بتبويب نشط ثانٍ، وتحميل التقرير لا يتكرر أثناء polling."""
    assert "document.querySelectorAll('.nav-item').forEach" in template_content
    assert "document.querySelectorAll('.nav-item[data-view]').forEach" not in template_content
    assert 'let _loadingBatchReportId = null;' in template_content
    assert '_loadingBatchReportId !== activeItem.report_id' in template_content


def test_topbar_brand_is_anchored_without_menu_toggle(template_content):
    """الشعار يبدأ من يمين الهيدر مباشرة بلا زر قائمة يفصل بينهما."""
    assert 'class="topbar-brand"' in template_content
    assert '.topbar-brand {' in template_content
    assert 'margin-inline-end: auto' in template_content
    assert 'id="mobile-menu-toggle"' not in template_content
    assert 'id="sidebar-mobile-overlay"' not in template_content


def test_date_filter_is_compact_and_functional(template_content):
    """فلتر التاريخ يستخدم مكوّناً مدمجاً ويرسل حدود الفترة للخادم."""
    assert 'segmented-filter-bar' not in template_content
    assert 'custom-date-picker-badge' not in template_content
    assert 'arabic-datepicker-popover' not in template_content
    assert '.date-range-filter {' in template_content
    assert 'id="reports-date-from"' in template_content
    assert 'id="reports-date-to"' in template_content
    assert "function applyDateFilter(viewKey)" in template_content
    assert "params.set('date_from', range.from)" in template_content
    assert "params.set('date_to', range.to)" in template_content


def test_all_sidebar_items_are_right_aligned_with_white_icons_and_red_review_badge(template_content):
    """كل روابط القائمة تبدأ من اليمين وتستخدم أيقونات بيضاء، مع إبراز عداد المراجعات بالأحمر."""
    assert '#badge-initial-review-count {' in template_content
    nav_block = re.search(r'\.nav-item\s*\{([^}]+)\}', template_content)
    assert nav_block is not None
    assert 'justify-content: flex-start' in nav_block.group(1)
    assert 'text-align: right' in nav_block.group(1)
    assert 'direction: rtl' in nav_block.group(1)
    assert '.nav-item .nav-icon-svg {' in template_content
    assert 'stroke: #ffffff' in template_content
    assert template_content.count('class="nav-icon-svg" aria-hidden="true"') >= 13
    assert 'color: #fca5a5' in template_content


def test_every_view_remains_inside_main_content(template_content):
    """منع رجوع كسر الهيكل الذي كان يخرج صفحات الرسائل والتدقيق خارج main."""
    main_match = re.search(r'<main class="main-content"[^>]*>(.*?)</main>', template_content, re.S)
    assert main_match is not None
    main_markup = main_match.group(1)
    for view_id in ('view-dashboard', 'view-reports', 'view-database', 'view-theses', 'view-audit', 'view-help'):
        assert f'id="{view_id}"' in main_markup

    report_markup = main_markup.split('id="view-reports"', 1)[1].split('id="view-database"', 1)[0]
    assert len(re.findall(r'<div\b', report_markup)) == len(re.findall(r'</div\s*>', report_markup))


def test_review_workflow_tabs_are_visible_in_sidebar(template_content):
    """حالات التحكيم الأساسية لها روابط واضحة بدلاً من بقائها صفحات مخفية."""
    assert 'id="nav-initial-review"' in template_content
    assert '<span class="nav-item-label">قيد المراجعة</span>' in template_content
    assert 'id="nav-preliminary"' in template_content
    assert '<span class="nav-item-label">القبول المبدئي</span>' in template_content
    assert 'id="nav-final-accepted"' in template_content
    assert '>القبول النهائي<' in template_content
    assert 'id="nav-rejected"' in template_content
    assert '>الرسائل المرفوضة<' in template_content


def test_report_primary_accept_action_is_preliminary(template_content):
    """زر التقرير يرسل للقبول المبدئي ولا يتجاوز مرحلة التحكيم إلى الاعتماد النهائي."""
    assert 'id="btn-accept-preliminary" onclick="acceptInitialPaper()"' in template_content
    assert '<span>قبول مبدئي</span>' in template_content
    assert "const btnAccept = document.getElementById('btn-accept-preliminary');" in template_content
    assert "showToast('تم القبول المبدئي للبحث بنجاح" in template_content
    assert "switchView('preliminary');" in template_content
    assert 'id="btn-accept-initial" onclick="acceptFinalPaper()"' not in template_content


def test_rejected_history_score_is_visually_separate(template_content):
    """تشابه المرفوضات يظهر كمؤشر إعادة تقديم ولا يختلط بنسبة الاستلال الرسمية."""
    assert 'id="rejected-history-card"' in template_content
    assert 'id="rejected-history-pct"' in template_content
    assert 'id="rejected-history-details"' in template_content
    assert 'id="rejected-history-sources"' in template_content
    assert 'هذه النسبة منفصلة ولا تدخل في نسبة الاستلال الرسمية.' in template_content
    assert "const rejectedHistoryPct = report.rejected_history_pct || 0;" in template_content


def test_current_scan_opens_without_report_archive(template_content):
    """نتيجة الرفع الحالية تستبدل أرشيف التقارير بدلاً من الظهور أسفله."""
    assert 'id="report-archive-panel"' in template_content
    assert 'if (archivePanel) archivePanel.hidden = showDetail;' in template_content
    assert template_content.count("switchView('reports', true);") >= 4
    assert "function openReportsArchive()" in template_content
    assert "function openFinalAcceptedReports()" in template_content


def test_new_scan_replaces_stale_report_workspace(template_content):
    """قبول فحص جديد يخفي نتيجة البحث السابق حتى تكتمل النتيجة الجديدة."""
    assert '#report-detail-panel.report-workspace-loading > :not(:first-child):not(#batch-switcher-bar)' in template_content
    assert 'function prepareReportWorkspaceForNewScan(message)' in template_content
    assert "detailPanel.classList.toggle('report-workspace-loading', visible)" in template_content
    assert "prepareReportWorkspaceForNewScan('جاري فحص الرسالة وتجهيز نتيجتها...')" in template_content
    assert "prepareReportWorkspaceForNewScan('تم استلام الملف — جاري بدء الفحص...')" in template_content
    assert "prepareReportWorkspaceForNewScan('جاري إعادة فحص البحث — 0%')" in template_content


def test_tables_and_forms_have_mobile_fallbacks(template_content):
    """الجداول قابلة للتمرير والنماذج متعددة الأعمدة تتكدس على الشاشات الصغيرة."""
    assert 'function initializeResponsiveTables()' in template_content
    assert "wrapper.className = 'table-scroll';" in template_content
    assert '.table-scroll .custom-table {' in template_content
    assert '.main-content [style*="grid-template-columns"] {' in template_content
    assert 'grid-template-columns: minmax(0, 1fr) !important;' in template_content


def test_employee_first_login_is_a_locked_modal_not_inline_content(template_content):
    """إعداد الموظف الأول يغطي التطبيق ويعزل واجهة الجلسة السابقة بالكامل."""
    assert '.first-login-overlay {' in template_content
    assert 'position: fixed;' in template_content
    assert 'z-index: 200100;' in template_content
    assert '.first-login-card {' in template_content
    assert 'id="first-login-overlay" class="first-login-overlay" role="dialog" aria-modal="true" aria-hidden="true"' in template_content
    assert 'function setFirstLoginLock(locked)' in template_content
    assert "document.querySelectorAll('.topbar, .app-container')" in template_content
    assert 'shell.inert = locked;' in template_content
    assert "switchView(normalizeUserRole(currentUser?.role) === 'employee' ? 'upload' : 'dashboard');" in template_content
    assert "overlay.setAttribute('aria-hidden', 'false');" in template_content
