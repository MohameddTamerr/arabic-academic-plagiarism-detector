# -*- coding: utf-8 -*-
"""
تهيئة تطبيق Flask وتجميع الطبقات والمسارات (App Factory):
- ضبط الإعدادات الآمنة والـ Secret Key.
- تسجيل كافة Blueprints للمسارات المنفصلة.
- تهيئة قاعدة البيانات والتأكد من جداول SQLAlchemy عند الإقلاع.
"""

import os
from pathlib import Path
from flask import Flask, render_template, send_file

import config
from app.repositories.base_repo import init_database
from app.routes.auth_routes import auth_bp
from app.routes.paper_routes import paper_bp
from app.routes.scan_routes import scan_bp
from app.routes.report_routes import report_bp
from app.routes.settings_routes import settings_bp
from app.routes.system_routes import system_bp
from app.routes.batch_routes import batch_bp


def create_app() -> Flask:
    template_dir = config.BASE_DIR / 'templates'
    static_dir = config.BASE_DIR / 'static'

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir)
    )

    # إعدادات الأمان
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

    # تهيئة قاعدة البيانات والجداول
    init_database()

    # تسجيل الـ Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(paper_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(batch_bp)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/static/logo.png')
    @app.route('/logo.png')
    def get_logo():
        logo_path = config.BASE_DIR / 'Police-Academy-College-of-Graduate-Studies.png'
        if logo_path.exists():
            return send_file(str(logo_path), mimetype='image/png')
        return '', 404

    return app
