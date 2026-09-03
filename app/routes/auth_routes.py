# -*- coding: utf-8 -*-
"""
مسارات المصادقة والأمان وإدارة المستخدمين (Authentication & Security Routes):
- تسجيل الدخول الآمن المشفر بـ bcrypt.
- دعم شاشة إعداد المدير لأول مرة (First-Time Setup).
- إدارة طلبات استعادة وتعيين كلمات المرور.
"""

from flask import Blueprint, request, jsonify
from app.repositories import user_repo

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route('/api/auth/status', methods=['GET'])
def get_auth_status():
    """التحقق من حالة النظام وهل يحتاج لإعداد المدير الأول."""
    return jsonify({
        'needs_first_time_setup': user_repo.is_first_time_setup()
    })


@auth_bp.route('/api/auth/setup_first_admin', methods=['POST'])
@auth_bp.route('/api/auth/setup_admin', methods=['POST'])
def setup_first_admin():
    """إنشاء حساب مدير النظام الأول في مرحلة الإعداد الأولى فقط."""
    if not user_repo.is_first_time_setup():
        return jsonify({'success': False, 'error': 'تم إعداد مدير النظام مسبقاً.'}), 400

    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()

    ok, msg = user_repo.create_initial_admin(username, password, full_name)
    if ok:
        user, _ = user_repo.authenticate_or_reset_user(username, password)
        return jsonify({'success': True, 'message': msg, 'user': user})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """تسجيل الدخول مع الدعم التلقائي لاعتماد كلمة المرور وترقية الهاش القديم."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    user, was_reset = user_repo.authenticate_or_reset_user(username, password)
    if user:
        return jsonify({
            'success': True,
            'user': user,
            'password_was_reset': was_reset,
            'message': 'تم اعتماد كلمة المرور الجديدة بنجاح وتسجيل دخولك إلى المنظومة!' if was_reset else 'مرحباً بك في المنظومة الأكاديمية'
        })
    return jsonify({'success': False, 'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401


@auth_bp.route('/api/auth/change_password', methods=['POST'])
def change_password_route():
    """تغيير كلمة المرور من قبل المستخدم."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    old_pass = data.get('old_password', '').strip()
    new_pass = data.get('new_password', '').strip()

    if len(new_pass) < 4:
        return jsonify({'success': False, 'error': 'كلمة المرور الجديدة يجب ألا تقل عن 4 خانات'}), 400

    if user_repo.change_password(username, old_pass, new_pass):
        return jsonify({'success': True, 'message': 'تم تغيير كلمة المرور بنجاح'})
    return jsonify({'success': False, 'error': 'كلمة المرور الحالية غير صحيحة'}), 400


@auth_bp.route('/api/admin/users', methods=['GET', 'POST'])
def handle_users():
    """إدارة المستخدمين (عرض وإضافة)."""
    if request.method == 'GET':
        return jsonify({'users': user_repo.get_users_list()})

    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '')
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    role = data.get('role', 'employee')

    ok, msg = user_repo.add_user(username, password, full_name, role)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/forgot_password/request', methods=['POST'])
def forgot_password_request_route():
    """تقديم طلب استعادة كلمة مرور من الموظف لمدير النظام."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    new_password = data.get('new_password', '').strip()

    ok, msg = user_repo.request_password_reset(username, new_password)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/password_resets', methods=['GET'])
def get_password_resets_route():
    return jsonify({'requests': user_repo.get_password_reset_requests()})


@auth_bp.route('/api/admin/password_resets/<int:req_id>/approve', methods=['POST'])
def approve_password_reset_route(req_id):
    ok, msg = user_repo.approve_password_reset(req_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/password_resets/<int:req_id>/decline', methods=['POST'])
def decline_password_reset_route(req_id):
    ok, msg = user_repo.decline_password_reset(req_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/users/<int:user_id>/reset_password', methods=['POST'])
def reset_employee_pass_route(user_id):
    data = request.get_json(silent=True) or request.form or {}
    new_pass = data.get('new_password', '').strip()
    ok, msg = user_repo.admin_reset_user_password(user_id, new_pass)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/emergency_reset', methods=['POST'])
def emergency_reset_route():
    from plagiarism_detector.core.db import reset_admin_with_master_key
    data = request.get_json(silent=True) or request.form or {}
    master_key = data.get('master_key', '').strip()
    new_pass = data.get('new_password', '').strip()
    ok, msg = reset_admin_with_master_key(master_key, new_pass)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400
