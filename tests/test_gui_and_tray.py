# -*- coding: utf-8 -*-
"""
اختبارات وحدة التحكم الرسومية المدمجة وأيقونة شريط المهام (GUI & Tray Controller Unit Tests):
- التحقق من الإقلاع المخفي افتراضياً (Hidden Default Startup).
- التحقق من إظهار وإخفاء لوحة الإدارة عند الطلب (On-Demand Show/Hide).
- التحقق من حماية العمليات الإدارية بتأكيد المستخدم (Admin Action Confirmations).
- التحقق من تهيئة أيقونة شريط المهام ومعالجة الأوامر.
"""

import os
import sys
import tkinter as tk
import pytest
from unittest.mock import MagicMock, patch

import app
import config
from app.single_exe.app_controller import AppController
from app.single_exe.gui_controller import ControlCenterGUI
from app.single_exe.tray_controller import TrayController


@pytest.fixture(scope="module")
def shared_tk_root():
    """مقبض نافذة Tk مشترك على مستوى الحزمة لتفادي إعادة تهيئة مفسر Tcl."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        yield None


def test_control_center_starts_hidden(shared_tk_root):
    """التحقق من أن لوحة التحكم تبدأ مخفية افتراضياً ولا تظهر كنافذة منبثقة تلقائياً."""
    if shared_tk_root is None:
        pytest.skip("Tkinter not available in environment")

    mock_controller = MagicMock(spec=AppController)
    mock_controller.port = 5000
    mock_controller.lan_ip = "127.0.0.1"
    mock_controller.num_workers = 2
    mock_controller.logs_dir = config.LOGS_DIR

    gui = ControlCenterGUI(mock_controller, start_hidden=True, root=shared_tk_root)
    state = gui.root.state()
    assert state == "withdrawn", f"Expected state 'withdrawn' but got '{state}'"
    assert "System Administration Console" in gui.root.title()


def test_control_center_show_and_hide_transitions(shared_tk_root):
    """التحقق من التبديل السلس بين إظهار وإخفاء لوحة الإدارة."""
    if shared_tk_root is None:
        pytest.skip("Tkinter not available in environment")

    mock_controller = MagicMock(spec=AppController)
    mock_controller.port = 5000
    mock_controller.lan_ip = "127.0.0.1"
    mock_controller.num_workers = 2
    mock_controller.logs_dir = config.LOGS_DIR

    gui = ControlCenterGUI(mock_controller, start_hidden=True, root=shared_tk_root)
    assert gui.root.state() == "withdrawn"
    
    # إظهار اللوحة
    gui.show_admin_console()
    gui.root.update()
    assert gui.root.state() == "normal"
    
    # إخفاء اللوحة مجدداً (كما عند الضغط على زر X أو زر إخفاء)
    gui.hide_admin_console()
    gui.root.update()
    assert gui.root.state() == "withdrawn"


def test_admin_backup_confirmation_protection(shared_tk_root):
    """التحقق من طلب تأكيد صريح قبل تنفيذ النسخ الاحتياطي في لوحة الإدارة."""
    if shared_tk_root is None:
        pytest.skip("Tkinter not available in environment")

    mock_controller = MagicMock(spec=AppController)
    mock_controller.port = 5000
    mock_controller.lan_ip = "127.0.0.1"
    mock_controller.num_workers = 2
    mock_controller.logs_dir = config.LOGS_DIR

    gui = ControlCenterGUI(mock_controller, start_hidden=True, root=shared_tk_root)

    # حالة 1: المستخدم يلغي التأكيد -> لا يتم استدعاء create_backup
    with patch('tkinter.messagebox.askyesno', return_value=False) as mock_ask:
        gui.create_backup_with_confirmation()
        mock_ask.assert_called_once()
        mock_controller.create_backup.assert_not_called()

    # حالة 2: المستخدم يؤكد -> يتم استدعاء create_backup
    mock_controller.create_backup.return_value = {
        'backup_file': 'test.zip',
        'size_mb': 1.0,
        'research_count': 5,
        'sha256_checksum': 'abc123'
    }
    with patch('tkinter.messagebox.askyesno', return_value=True), \
         patch('tkinter.messagebox.showinfo'):
        gui.create_backup_with_confirmation()
        mock_controller.create_backup.assert_called_once_with(label="admin_console")


def test_admin_diagnostic_confirmation_protection(shared_tk_root):
    """التحقق من طلب تأكيد صريح قبل تصدير حزمة التشخيص."""
    if shared_tk_root is None:
        pytest.skip("Tkinter not available in environment")

    mock_controller = MagicMock(spec=AppController)
    mock_controller.port = 5000
    mock_controller.lan_ip = "127.0.0.1"
    mock_controller.num_workers = 2
    mock_controller.logs_dir = config.LOGS_DIR

    gui = ControlCenterGUI(mock_controller, start_hidden=True, root=shared_tk_root)

    # حالة 1: إلغاء التأكيد
    with patch('tkinter.messagebox.askyesno', return_value=False):
        gui.create_diagnostic_with_confirmation()
        mock_controller.create_diagnostic_package.assert_not_called()

    # حالة 2: تأكيد
    mock_controller.create_diagnostic_package.return_value = "diagnostic.zip"
    with patch('tkinter.messagebox.askyesno', return_value=True), \
         patch('tkinter.messagebox.showinfo'):
        gui.create_diagnostic_with_confirmation()
        mock_controller.create_diagnostic_package.assert_called_once()


def test_tray_controller_menu_commands():
    """التحقق من توجيه أوامر شريط المهام بدقة إلى الواجهة ووحدة التحكم."""
    mock_controller = MagicMock(spec=AppController)
    mock_controller.port = 5000
    mock_controller.lan_ip = "127.0.0.1"
    mock_controller.num_workers = 2
    mock_controller.logs_dir = config.LOGS_DIR

    mock_gui = MagicMock(spec=ControlCenterGUI)
    tray = TrayController(mock_controller, mock_gui)

    # 1. فتح النظام في المتصفح
    with patch('webbrowser.open') as mock_browser:
        tray._handle_menu_command(TrayController.ID_OPEN_SYSTEM)
        mock_browser.assert_called_once_with("http://127.0.0.1:5000")

    # 2. لوحة إدارة النظام
    tray._handle_menu_command(TrayController.ID_ADMIN_CONSOLE)
    mock_gui.dispatch_to_gui.assert_called_with(mock_gui.show_admin_console)

    # 3. إيقاف النظام
    tray._handle_menu_command(TrayController.ID_EXIT_SYSTEM)
    mock_gui.dispatch_to_gui.assert_called_with(mock_gui.on_exit_request)
