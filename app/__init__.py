# -*- coding: utf-8 -*-
"""
تهيئة تطبيق Flask وتجميع الطبقات والمسارات (App Factory):
- ضبط الإعدادات الآمنة والـ Secret Key.
- تهيئة منظومة التسجيل الهيكلي وتدوير السجلات المحلية.
- تسجيل برمجية معرف تتبع الطلب (Request ID Middleware).
- تسجيل معالجات الأخطاء المركزية وحماية الاستجابات.
- تسجيل كافة Blueprints للمسارات المنفصلة.
- تهيئة قاعدة البيانات والتأكد من جداول SQLAlchemy عند الإقلاع.
"""

import os
import logging
from pathlib import Path
from flask import Flask, render_template, send_file

import config

logger = logging.getLogger(__name__)
from app.repositories.base_repo import init_database
from app.logging_config import setup_logging
from app.middleware.request_id import setup_request_id
from app.errors.handlers import register_error_handlers

from app.routes.auth_routes import auth_bp
from app.routes.paper_routes import paper_bp
from app.routes.scan_routes import scan_bp
from app.routes.report_routes import report_bp
from app.routes.settings_routes import settings_bp
from app.routes.system_routes import system_bp
from app.routes.batch_routes import batch_bp
from app.routes.audit_routes import audit_bp
from app.routes.job_routes import job_bp
from app.routes.recovery_routes import recovery_bp
from app.routes.user_routes import user_bp
from app.routes.thesis_routes import thesis_bp
from app.routes.common_phrases_routes import common_phrases_bp


def create_app() -> Flask:
    # 1. تهيئة التسجيل المركزي
    setup_logging()

    bundle_dir = getattr(config, 'BUNDLE_DIR', config.BASE_DIR)
    template_dir = bundle_dir / 'templates'
    if not template_dir.exists():
        template_dir = config.BASE_DIR / 'templates'
    static_dir = bundle_dir / 'static'
    if not static_dir.exists():
        static_dir = config.BASE_DIR / 'static'

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir)
    )

    # إعدادات الأمان
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    app.config['SESSION_COOKIE_HTTPONLY'] = getattr(config, 'AUTH_COOKIE_HTTPONLY', True)
    app.config['SESSION_COOKIE_SAMESITE'] = getattr(config, 'AUTH_COOKIE_SAMESITE', 'Lax')
    app.config['SESSION_COOKIE_SECURE'] = getattr(config, 'AUTH_COOKIE_SECURE', False)

    # 2. تسجيل معرف الطلب ومعالجات الأخطاء وفحص CSRF
    setup_request_id(app)
    register_error_handlers(app)

    from app.security.csrf import validate_csrf_token
    @app.before_request
    def csrf_protect():
        err = validate_csrf_token()
        if err:
            return err

    # 3. تهيئة قاعدة البيانات والجداول واستدراك المهام المنقطعة
    init_database()
    try:
        from app.services import job_queue_service
        job_queue_service.recover_interrupted_jobs()
    except Exception as e:
        logger.warning(f"تحذير أثناء استدراك المهام المنقطعة عند الإقلاع: {e}")

    # 4. تسجيل الـ Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(paper_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(job_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(thesis_bp)
    app.register_blueprint(common_phrases_bp)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/static/logo.png')
    @app.route('/logo.png')
    def get_logo():
        bundle_dir = getattr(config, 'BUNDLE_DIR', config.BASE_DIR)
        logo_path = bundle_dir / 'Police-Academy-College-of-Graduate-Studies.png'
        if not logo_path.exists():
            logo_path = config.BASE_DIR / 'Police-Academy-College-of-Graduate-Studies.png'
        if logo_path.exists():
            return send_file(str(logo_path), mimetype='image/png')
        return '', 404

    return app
