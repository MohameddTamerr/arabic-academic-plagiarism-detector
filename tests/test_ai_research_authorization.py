# -*- coding: utf-8 -*-
"""
Tests for AI Research Mode Authorization & Security Audit (TASK 2).
Ensures standard scans cannot enable experimental AI detection without proper authorization.
"""
import pytest
from app.security.permissions import Role, Permission
from app.routes.scan_routes import is_ai_research_authorized
from app.services import audit_service


def test_ai_research_unauthorized_user_denied(monkeypatch):
    """A standard user without admin/settings privileges cannot enable AI research mode."""
    # Ensure system setting is False
    monkeypatch.setattr('app.routes.scan_routes.get_current_settings', lambda: {'enable_ai_research_mode': False})

    unauthorized_users = [
        {'id': 10, 'username': 'student_user', 'role': Role.EMPLOYEE},
        {'id': 11, 'username': 'clerk_user', 'role': Role.DATA_ENTRY},
        {'id': 12, 'username': 'reviewer_user', 'role': Role.REVIEWER},
        None,
    ]

    for user in unauthorized_users:
        authorized = is_ai_research_authorized(user, requested_enable=True)
        assert authorized is False, f"User {user} should NOT be authorized to enable AI research mode"


def test_ai_research_authorized_admin(monkeypatch):
    """System admins and unit managers can enable AI research mode when requested."""
    monkeypatch.setattr('app.routes.scan_routes.get_current_settings', lambda: {'enable_ai_research_mode': False})

    authorized_users = [
        {'id': 1, 'username': 'sysadmin', 'role': Role.SYSTEM_ADMIN},
        {'id': 2, 'username': 'legacy_admin', 'role': Role.LEGACY_ADMIN},
        {'id': 3, 'username': 'manager', 'role': Role.UNIT_MANAGER},
    ]

    for user in authorized_users:
        authorized = is_ai_research_authorized(user, requested_enable=True)
        assert authorized is True, f"Admin {user['role']} must be authorized to enable AI research mode"


def test_ai_research_not_requested_returns_false():
    """If enable_ai_research is False or 0, always returns False regardless of role."""
    admin_user = {'id': 1, 'username': 'sysadmin', 'role': Role.SYSTEM_ADMIN}
    assert is_ai_research_authorized(admin_user, requested_enable=False) is False


def test_ai_research_institutional_setting_override(monkeypatch):
    """If the institutional system setting has enable_ai_research_mode=True, it is allowed."""
    monkeypatch.setattr('app.routes.scan_routes.get_current_settings', lambda: {'enable_ai_research_mode': True})
    normal_user = {'id': 10, 'username': 'student_user', 'role': Role.EMPLOYEE}
    assert is_ai_research_authorized(normal_user, requested_enable=True) is True
