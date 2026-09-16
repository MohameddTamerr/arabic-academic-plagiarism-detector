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
    assert 'class="custom-toast-message"' in template_content
    assert '.custom-toast-message {' in template_content
    assert '.toast-container { position:fixed;bottom:24px;left:24px' not in template_content


def test_mobile_sidebar_is_off_canvas_and_accessible(template_content):
    """القائمة الجانبية تتحول إلى قائمة منزلقة قابلة للفتح والإغلاق على الهاتف."""
    assert 'id="mobile-menu-toggle"' in template_content
    assert 'id="sidebar-mobile-overlay"' in template_content
    assert '.sidebar.mobile-open {' in template_content
    assert 'function toggleMobileSidebar(forceOpen)' in template_content
    assert "toggle.setAttribute('aria-expanded', String(shouldOpen));" in template_content


def test_tables_and_forms_have_mobile_fallbacks(template_content):
    """الجداول قابلة للتمرير والنماذج متعددة الأعمدة تتكدس على الشاشات الصغيرة."""
    assert 'function initializeResponsiveTables()' in template_content
    assert "wrapper.className = 'table-scroll';" in template_content
    assert '.table-scroll .custom-table {' in template_content
    assert '.main-content [style*="grid-template-columns"] {' in template_content
    assert 'grid-template-columns: minmax(0, 1fr) !important;' in template_content
