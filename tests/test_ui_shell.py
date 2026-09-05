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
