"""Regression checks for the canonical system-admin browser experience."""

from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def test_system_admin_is_rendered_as_superadmin_not_employee():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "function normalizeUserRole(role)" in html
    assert "function isSystemAdmin(user = currentUser)" in html
    assert "'system_admin', 'superadmin', 'super_admin', 'sysadmin'" in html
    assert "const isAdmin = isSystemAdmin(currentUser);" in html
    assert "badgeEl.innerText = currentUser.role_label_ar || (isAdmin ? 'مدير النظام التقني'" in html


def test_admin_only_navigation_does_not_use_legacy_exact_role_checks():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "currentUser.role !== 'admin'" not in html
    assert "currentUser.role === 'admin'" not in html
    assert "if (!isSystemAdmin(currentUser))" in html
    assert "if (count > 0 && isSystemAdmin(currentUser))" in html


def test_admin_access_does_not_force_entire_views_into_flex_layout():
    html = TEMPLATE.read_text(encoding="utf-8")
    start = html.index("document.querySelectorAll('.admin-only')")
    end = html.index("// التحكم في أزرار اتخاذ القرار", start)
    visibility_block = html[start:end]

    assert "el.style.display = isAdmin ? 'flex' : 'none';" not in visibility_block
    assert "el.style.removeProperty('display');" in visibility_block
    assert "el.style.display = 'none';" in visibility_block


def test_admin_shell_keeps_sidebar_inside_viewport():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "flex: 0 0 260px;" in html
    assert "flex: 1 1 0;" in html
    assert "width: 0;" in html
    assert ".app-container" in html and "min-width: 0;" in html
    assert "minmax(min(320px, 100%), 1fr)" in html
