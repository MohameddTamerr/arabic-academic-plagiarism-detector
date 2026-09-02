# -*- coding: utf-8 -*-
"""
خادم Web Flask خفيف يربط الواجهة الرسومية بمحرك الكشف وقاعدة البيانات.
يعمل محليًا بالكامل بدون إنترنت على http://localhost:5000
"""

import os
import sys
import json
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response

# ── تأكد من إضافة مسار المشروع والـ vendor ────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, 'vendor')
for _p in [_HERE, _VENDOR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from plagiarism_detector.core import db, detector
from plagiarism_detector.core.extractor import extract_text
from plagiarism_detector.core.normalize import normalize_arabic, detect_cheating_manipulation, clean_cheating_text
from plagiarism_detector.core.ai_detector import analyze_ai_generation
from plagiarism_detector.core.categorizer import categorize_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 1000 * 1024 * 1024  # 1 GB max file upload (دعم الملفات والمجلات الكبيرة حتى 1 جيجابايت)

# تهيئة قاعدة البيانات عند بدء الخادم
db.init_db()

# تخزين مؤقت لآخر الأبحاث المفحوصة للنص الخام
_LAST_ANALYZED_TEXTS = {}


@app.route('/')
def index():
    """الصفحة الرئيسية للتطبيق."""
    return render_template('index.html')


@app.route('/static/logo.png')
@app.route('/logo.png')
def get_logo():
    """تقديم شعار أكاديمية الشرطة - كلية الدراسات العليا."""
    logo_path = os.path.join(_HERE, 'Police-Academy-College-of-Graduate-Studies.png')
    if os.path.exists(logo_path):
        return send_file(logo_path, mimetype='image/png')
    return '', 404



@app.route('/api/stats', methods=['GET'])
def get_stats():
    """إرجاع إحصائيات لوحة التحكم الحقيقية من قاعدة البيانات."""
    paper_count = db.get_paper_count()
    stats = db.get_reports_stats_db()
    recent = db.get_recent_reports_db(limit=10)

    recent_reports = []
    for r in recent:
        recent_reports.append({
            'id': r['id'],
            'title': r['title'],
            'author': r.get('author', 'غير محدد'),
            'date': str(r['created_at'])[:16],
            'pct': r['overall_pct'],
            'status': r.get('status', 'مفحوص')
        })

    return jsonify({
        'total_papers': paper_count,
        'total_scans': stats['total_scans'],
        'avg_plagiarism': stats['avg_plagiarism'],
        'preliminary_count': stats.get('preliminary_count', 0),
        'final_count': stats.get('final_count', 0),
        'pending_initial_count': stats.get('pending_initial_count', 0),
        'recent_reports': recent_reports
    })


@app.route('/api/papers', methods=['GET'])
def list_papers():
    """إرجاع قائمة الأبحاث في قاعدة البيانات مع دعم البحث والتصفح."""
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    all_papers = db.get_all_papers()

    if query:
        norm_q = normalize_arabic(query)
        filtered = []
        for p in all_papers:
            t_norm = normalize_arabic(p.get('title', ''))
            a_norm = normalize_arabic(p.get('author', ''))
            c_norm = normalize_arabic(p.get('category', ''))
            d_norm = str(p.get('added_at', ''))

            if norm_q in t_norm or norm_q in a_norm or norm_q in c_norm or norm_q in d_norm or query.lower() in (p.get('author', '') + ' ' + p.get('title', '')).lower():
                filtered.append(p)
        all_papers = filtered

    total = len(all_papers)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_papers[start:end]

    for p in paginated:
        ext = os.path.splitext(p.get('file_path', ''))[1].upper().replace('.', '')
        p['file_type'] = ext if ext else 'TXT'
        if 'category' not in p:
            p['category'] = 'عام'

    return jsonify({
        'papers': paginated,
        'total': total,
        'page': page,
        'total_pages': max(1, (total + per_page - 1) // per_page)
    })


@app.route('/api/papers', methods=['POST'])
def add_paper():
    """إضافة بحث جديد إلى قاعدة البيانات."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    text = request.form.get('text', '').strip()
    file_path = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        filename = file.filename
        if not title:
            title = os.path.splitext(filename)[0]

        temp_dir = Path(_HERE) / 'temp_uploads'
        temp_dir.mkdir(exist_ok=True)
        save_path = temp_dir / filename
        file.save(save_path)
        file_path = str(save_path)
        extracted = extract_text(file_path)
        if extracted.strip():
            text = extracted

    if not title or not text:
        return jsonify({'error': 'العنوان والنص مطلوبان'}), 400

    if db.paper_exists(title):
        return jsonify({'error': 'يوجد بحث بنفس العنوان بالفعل'}), 400

    category = categorize_text(text)
    pid = db.add_paper(title=title, full_text=text, file_path=file_path, category=category, author=author)
    db.invalidate_index()
    detector.build_index()

    return jsonify({'success': True, 'id': pid, 'title': title, 'author': author, 'category': category})


@app.route('/api/papers/<int:paper_id>', methods=['DELETE'])
def delete_paper(paper_id):
    """حذف بحث من قاعدة البيانات."""
    db.delete_paper(paper_id)
    db.invalidate_index()
    detector.build_index()
    return jsonify({'success': True})


@app.route('/api/papers/<int:paper_id>/update', methods=['POST', 'PUT'])
def update_paper_endpoint(paper_id):
    """تعديل عنوان أو اسم الباحث أو تخصص أو تاريخ بحث مرجعي وإعادة بناء الفهرس."""
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    added_at = request.form.get('added_at')
    db.update_paper(paper_id, title=title, author=author, category=category, added_at=added_at)
    db.invalidate_index()
    detector.build_index()
    return jsonify({'success': True})


@app.route('/api/clear-db', methods=['POST', 'DELETE'])
def clear_database():
    """حذف كافة البيانات والأبحاث والتقارير من قاعدة البيانات بالكامل."""
    db.clear_all_data()
    detector.build_index()
    return jsonify({'success': True, 'message': 'تم تفريغ كافة البيانات في قاعدة البيانات بنجاح'})


from concurrent.futures import ThreadPoolExecutor
import uuid
import datetime

# تهيئة حوض مسارات المعالجة بالخلفية للفحص غير المتزامن (Background Worker Threads)
_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_SCAN_TASKS = {}


def _cleanup_old_temp_files():
    """حذف الملفات المؤقتة التي مضى عليها أكثر من 24 ساعة للحفاظ على مساحة القرص."""
    try:
        temp_dir = Path(_HERE) / 'temp_uploads'
        if not temp_dir.exists():
            return
        now_ts = datetime.datetime.now().timestamp()
        for f in temp_dir.iterdir():
            if f.is_file():
                age_hours = (now_ts - f.stat().st_mtime) / 3600.0
                if age_hours > 24.0:
                    try:
                        f.unlink()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"خطأ أثناء تنظيف الملفات المؤقتة: {e}")


# تنظيف دوري أولي للملفات المؤقتة عند الإقلاع
_cleanup_old_temp_files()


def _run_background_scan(task_id: str, file_path: str, title: str, author: str, raw_text: str, file_name: str):
    """دالة فحص تعمل في الخلفية بالكامل وتحدّث مراحل التقدم لحظياً."""
    try:
        _SCAN_TASKS[task_id]['stage'] = 'جاري استخراج وقراءة النصوص من المستند...'
        _SCAN_TASKS[task_id]['progress'] = 20

        if file_path and os.path.exists(file_path):
            extracted = extract_text(file_path)
            if extracted.strip():
                raw_text = extracted

        if not raw_text.strip():
            _SCAN_TASKS[task_id]['status'] = 'error'
            _SCAN_TASKS[task_id]['error'] = 'لم يتم العثور على نصوص قابلة للقراءة في هذا الملف'
            return

        _SCAN_TASKS[task_id]['stage'] = 'جاري تنقية النصوص وكشف التلاعب بالمسافات والأحرف...'
        _SCAN_TASKS[task_id]['progress'] = 40
        cheating_res = detect_cheating_manipulation(raw_text)
        cleaned_text = clean_cheating_text(raw_text)

        _SCAN_TASKS[task_id]['stage'] = 'جاري مطابقة المتواليات ومقارنة النص بقاعدة الأبحاث المرجعية...'
        _SCAN_TASKS[task_id]['progress'] = 65
        report = detector.analyze_text(cleaned_text)

        _SCAN_TASKS[task_id]['stage'] = 'جاري كشف التوليد بالذكاء الاصطناعي وتصنيف التخصص...'
        _SCAN_TASKS[task_id]['progress'] = 85
        ai_res = analyze_ai_generation(cleaned_text)
        category = categorize_text(cleaned_text)

        report_id = str(uuid.uuid4())[:8]
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

        report['id'] = report_id
        report['title'] = title if title else (file_name if file_name else 'بحث جديد')
        report['author'] = author if author else 'غير محدد'
        report['date'] = now_str
        report['category'] = category
        report['cheating'] = cheating_res
        report['ai_analysis'] = ai_res
        report['file_path'] = file_path
        report['status'] = 'مفحوص'

        _LAST_ANALYZED_TEXTS[report_id] = {
            'title': report['title'],
            'author': report['author'],
            'text': cleaned_text,
            'category': category,
            'file_path': file_path
        }

        db.save_report_db(
            report_id=report_id,
            title=report['title'],
            overall_pct=report['overall_pct'],
            copied_pct=report['copied_pct'],
            para_pct=report['paraphrase_pct'],
            report_dict=report,
            category=category,
            status='مفحوص',
            author=report['author'],
            file_path=file_path
        )

        _SCAN_TASKS[task_id]['stage'] = 'اكتمل التحليل بنجاح!'
        _SCAN_TASKS[task_id]['progress'] = 100
        _SCAN_TASKS[task_id]['status'] = 'completed'
        _SCAN_TASKS[task_id]['result'] = report

    except Exception as e:
        logger.error(f"خطأ أثناء فحص المهمة {task_id}: {e}", exc_info=True)
        _SCAN_TASKS[task_id]['status'] = 'error'
        _SCAN_TASKS[task_id]['error'] = f'حدث خطأ أثناء المعالجة: {str(e)}'


@app.route('/api/analyze_async', methods=['POST'])
def analyze_async():
    """بدء فحص غير متزامن في الخلفية لضمان عدم توقف المتصفح حتى مع الملفات الضخمة."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_name = ''
    file_path = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        file_name = file.filename
        if not title:
            title = os.path.splitext(file_name)[0]

        temp_dir = Path(_HERE) / 'temp_uploads'
        temp_dir.mkdir(exist_ok=True)
        save_path = temp_dir / f"{uuid.uuid4().hex[:6]}_{file_name}"
        file.save(save_path)
        file_path = str(save_path)

    task_id = str(uuid.uuid4())[:10]
    _SCAN_TASKS[task_id] = {
        'task_id': task_id,
        'status': 'running',
        'progress': 10,
        'stage': 'جاري استلام الملف وبدء المعالجة...',
        'file_name': file_name or title or 'نص مدخل',
        'result': None,
        'error': None
    }

    _EXECUTOR.submit(_run_background_scan, task_id, file_path, title, author, raw_text, file_name)
    return jsonify({'task_id': task_id, 'status': 'queued'})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """استعلام عن تقدم مهمة الفحص في الخلفية."""
    task = _SCAN_TASKS.get(task_id)
    if not task:
        return jsonify({'error': 'المهمة غير موجودة'}), 404
    return jsonify(task)


# ── مسارات المصادقة والصلاحيات (Authentication & Roles - 100% Offline) ───
@app.route('/api/auth/login', methods=['POST'])
def login():
    """تسجيل الدخول مع الدعم التلقائي لاعتماد كلمة المرور الجديدة عند موافقة المدير."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    user, was_reset = db.authenticate_or_reset_user(username, password)
    if user:
        return jsonify({
            'success': True,
            'user': user,
            'password_was_reset': was_reset,
            'message': 'تم اعتماد وحفظ كلمة المرور الجديدة بنجاح وتسجيل دخولك إلى النظام!' if was_reset else 'مرحباً بك في المنظومة'
        })
    return jsonify({'success': False, 'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401


@app.route('/api/auth/change_password', methods=['POST'])
def change_pass():
    """تغيير كلمة المرور أوفلاين."""
    data = request.get_json(silent=True) or request.form
    username = data.get('username', '').strip()
    old_pass = data.get('old_password', '').strip()
    new_pass = data.get('new_password', '').strip()
    if len(new_pass) < 4:
        return jsonify({'success': False, 'error': 'كلمة المرور الجديدة يجب ألا تقل عن 4 خانات'}), 400
    if db.change_password(username, old_pass, new_pass):
        return jsonify({'success': True, 'message': 'تم تغيير كلمة المرور بنجاح'})
    return jsonify({'success': False, 'error': 'كلمة المرور الحالية غير صحيحة'}), 400


@app.route('/api/admin/users', methods=['GET', 'POST'])
def handle_users():
    """إدارة المستخدمين والموظفين (عرض وإضافة)."""
    if request.method == 'GET':
        return jsonify({'users': db.get_users_list()})
    
    data = request.get_json(silent=True) or request.form
    username = data.get('username', '')
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    role = data.get('role', 'employee')

    ok, msg = db.add_user(username, password, full_name, role)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400



@app.route('/api/auth/forgot_password/request', methods=['POST'])
def forgot_password_request_route():
    """إرسال طلب استعادة كلمة المرور من الموظف لمدير النظام مرفقاً بها كلمة المرور الجديدة."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    new_password = data.get('new_password', '').strip()
    ok, msg = db.request_password_reset(username, new_password)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@app.route('/api/admin/password_resets', methods=['GET'])
def get_password_resets_route():
    """استرجاع قائمة طلبات استعادة كلمة المرور للمدير."""
    requests = db.get_password_reset_requests()
    return jsonify({'requests': requests})


@app.route('/api/admin/password_resets/<int:req_id>/approve', methods=['POST'])
def approve_password_reset_route(req_id):
    """موافقة المدير على طلب استعادة كلمة المرور."""
    ok, msg = db.approve_password_reset(req_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@app.route('/api/admin/password_resets/<int:req_id>/decline', methods=['POST'])
def decline_password_reset_route(req_id):
    """رفض المدير لطلب استعادة كلمة المرور."""
    ok, msg = db.decline_password_reset(req_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400

@app.route('/api/auth/emergency_reset', methods=['POST'])
def emergency_reset_route():
    """استعادة كلمة مرور مدير النظام باستخدام مفتاح الأمان الرئيسي للطوارئ."""
    data = request.get_json(silent=True) or request.form
    master_key = data.get('master_key', '').strip()
    new_pass = data.get('new_password', '').strip()
    ok, msg = db.reset_admin_with_master_key(master_key, new_pass)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@app.route('/api/admin/users/<int:user_id>/reset_password', methods=['POST'])
def reset_employee_pass_route(user_id):
    """إعادة تعيين كلمة مرور موظف من قبل مدير النظام."""
    data = request.get_json(silent=True) or request.form
    new_pass = data.get('new_password', '').strip()
    ok, msg = db.admin_reset_user_password(user_id, new_pass)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


# ── مسارات الفحص الأولي (Initial Screening Queue) ─────────────────────────
@app.route('/api/reports/<report_id>/submit_to_admin', methods=['POST'])
def submit_to_admin_route(report_id):
    """إرسال البحث من قبل الموظف لمدير النظام للاعتماد والفحص الأولي."""
    data = request.get_json(silent=True) or request.form or {}
    employee_name = data.get('employee_name', 'موظف الفحص').strip()
    notes = data.get('notes', '').strip()

    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    db.submit_report_to_admin(report_id, employee_name, notes)
    return jsonify({
        'success': True,
        'id': report_id,
        'status': 'بانتظار الفحص الأولي',
        'message': 'تم إرسال البحث بنجاح إلى مدير النظام للفحص الأولي واتخاذ القرار'
    })


@app.route('/api/initial_reviews', methods=['GET'])
def get_initial_reviews_route():
    """استرجاع قائمة كافة الأبحاث المنتظرة في طابور الفحص الأولي لمدير النظام."""
    q = request.args.get('q', '').strip()
    papers = db.get_pending_initial_reviews_db(q)
    return jsonify({'papers': papers, 'count': len(papers)})


@app.route('/api/initial_reviews/count', methods=['GET'])
def get_initial_reviews_count_route():
    """استرجاع عدد الأبحاث المنتظرة في الفحص الأولي لتحديث دائرة الإشعارات."""
    count = db.get_pending_initial_reviews_count()
    return jsonify({'count': count})


# ── مسارات النسخ الاحتياطي وإدارة النظام (Admin & Backup Operations) ────
@app.route('/api/admin/backup', methods=['POST'])
def create_backup_endpoint():
    """إنشاء نسخة احتياطية فورية لقاعدة البيانات على القرص."""
    try:
        backup_path = db.create_database_backup()
        filename = os.path.basename(backup_path)
        return jsonify({'success': True, 'filename': filename, 'message': f'تم إنشاء النسخة الاحتياطية بنجاح: {filename}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/backups', methods=['GET'])
def list_backups_endpoint():
    """استرجاع قائمة النسخ الاحتياطية السابقة."""
    return jsonify({'backups': db.get_backups_list()})


@app.route('/api/admin/cleanup_temp', methods=['POST'])
def cleanup_temp_endpoint():
    """تنظيف الملفات المؤقتة."""
    _cleanup_old_temp_files()
    return jsonify({'success': True, 'message': 'تم تنظيف الملفات المؤقتة القديمة بنجاح'})


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """تحليل بحث جديد متزامن (للفحص الفردي السريع)."""
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    raw_text = request.form.get('text', '').strip()
    file_name = ''
    file_path = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        file_name = file.filename
        if not title:
            title = os.path.splitext(file_name)[0]

        temp_dir = Path(_HERE) / 'temp_uploads'
        temp_dir.mkdir(exist_ok=True)
        save_path = temp_dir / file_name
        file.save(save_path)
        file_path = str(save_path)
        extracted = extract_text(file_path)
        if extracted.strip():
            raw_text = extracted

    if not raw_text:
        return jsonify({'error': 'لم يتم العثور على نص لتحليله'}), 400

    cheating_res = detect_cheating_manipulation(raw_text)
    cleaned_text = clean_cheating_text(raw_text)
    ai_res = analyze_ai_generation(cleaned_text)
    category = categorize_text(cleaned_text)
    report = detector.analyze_text(cleaned_text)

    report_id = str(uuid.uuid4())[:8]
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    report['id'] = report_id
    report['title'] = title if title else (file_name if file_name else 'بحث جديد')
    report['author'] = author if author else 'غير محدد'
    report['date'] = now_str
    report['category'] = category
    report['cheating'] = cheating_res
    report['ai_analysis'] = ai_res
    report['file_path'] = file_path
    report['status'] = 'مفحوص'

    _LAST_ANALYZED_TEXTS[report_id] = {
        'title': report['title'],
        'author': report['author'],
        'text': cleaned_text,
        'category': category,
        'file_path': file_path
    }

    db.save_report_db(
        report_id=report_id,
        title=report['title'],
        overall_pct=report['overall_pct'],
        copied_pct=report['copied_pct'],
        para_pct=report['paraphrase_pct'],
        report_dict=report,
        category=category,
        status='مفحوص',
        author=report['author'],
        file_path=file_path
    )

    return jsonify(report)



@app.route('/api/reports/<report_id>/initial_accept', methods=['POST'])
def initial_accept_report(report_id):
    """تعديل حالة البحث إلى قبول مبدئي وتخزينه في قائمة الأبحاث المقبولة مبدئياً."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    db.set_report_status(report_id, 'قبول مبدئي')
    return jsonify({'success': True, 'id': report_id, 'status': 'قبول مبدئي'})


@app.route('/api/reports/<report_id>/reject', methods=['POST'])
def reject_report(report_id):
    """تعديل حالة البحث إلى مرفوض."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    db.set_report_status(report_id, 'مرفوض')
    return jsonify({'success': True, 'id': report_id, 'status': 'مرفوض'})


@app.route('/api/preliminary_papers', methods=['GET'])
def get_preliminary_papers():
    """استرجاع كل الأبحاث المقبولة مبدئياً ليتمكن المستخدم من فتحها في أي وقت."""
    papers = db.get_preliminary_reports()
    return jsonify({'papers': papers})


@app.route('/api/rejected_papers', methods=['GET'])
def get_rejected_papers():
    """استرجاع كل الأبحاث والباحثين المرفوضين."""
    papers = db.get_rejected_reports()
    return jsonify({'papers': papers})


@app.route('/api/reports/<report_id>', methods=['DELETE'])
def delete_report(report_id):
    """حذف تقرير من الأرشيف."""
    db.delete_report_db(report_id)
    return jsonify({'success': True})


@app.route('/api/reports/<report_id>/upload_latest_pdf', methods=['POST'])
def upload_latest_pdf(report_id):
    """رفع أحدث نسخة محدثة من ملف PDF لبحث مقبول مبدئياً."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'error': 'لم يتم اختيار ملف PDF جديد'}), 400

    file = request.files['file']
    filename = f"latest_{report_id}_{file.filename}"
    temp_dir = Path(_HERE) / 'temp_uploads'
    temp_dir.mkdir(exist_ok=True)
    save_path = temp_dir / filename
    file.save(save_path)
    file_path_str = str(save_path)

    extracted_text = extract_text(file_path_str)
    cleaned_text = clean_cheating_text(extracted_text) if extracted_text else ''

    db.update_report_latest_pdf(report_id, file_path_str, cleaned_text)
    return jsonify({'success': True, 'file_path': file_path_str, 'text_length': len(cleaned_text)})


@app.route('/api/reports/<report_id>/final_accept', methods=['POST'])
def final_accept_report(report_id):
    """القبول النهائي للبحث وإضافته رسمياً لقاعدة الأبحاث المرجعية الأساسية وإعادة بناء الفهرس."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    title = report.get('title', 'بحث بدون عنوان')
    author = report.get('author', 'غير محدد')
    category = report.get('category', 'عام')

    # التأكد من وجود نص أحدث PDF أو أخذ النص من التقرير الأصلي
    final_text = report.get('final_full_text', '')
    final_file_path = report.get('final_file_path', '') or report.get('file_path', '')

    if not final_text:
        if 'segments' in report and report['segments']:
            final_text = ' '.join([seg['text'] for seg in report['segments']])
        elif report_id in _LAST_ANALYZED_TEXTS:
            final_text = _LAST_ANALYZED_TEXTS[report_id]['text']

    if not final_text.strip():
        return jsonify({'error': 'تعذّر استخراج النص النهائي للبحث للقبول النهائي'}), 400

    if db.paper_exists(title):
        # إن كان موجودًا بالفعل بنفس العنوان، نقوم بإضافة وسم أو قبوله
        title = f"{title} (النسخة المحدثة)"

    pid = db.add_paper(title=title, full_text=final_text, file_path=final_file_path, category=category, author=author)
    db.set_report_status(report_id, 'قبول نهائي')
    db.invalidate_index()
    detector.build_index()

    return jsonify({'success': True, 'paper_id': pid, 'title': title, 'author': author, 'category': category})


@app.route('/api/accept_paper/<report_id>', methods=['POST'])
def accept_paper(report_id):
    """قبول البحث المضمون في التقرير وإضافته تلقائيًا إلى قاعدة الأبحاث."""
    return final_accept_report(report_id)


@app.route('/api/reports/<report_id>', methods=['GET'])
def get_report(report_id):
    """استرجاع تقرير سابق وتحديث نصوصه تلقائياً لضمان نظافة العرض من تشويه الخطوط."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    file_path = report.get('file_path', '')
    if file_path and os.path.exists(file_path):
        try:
            clean_txt = extract_text(file_path)
            if clean_txt.strip():
                cleaned_text = clean_cheating_text(clean_txt)
                fresh_rep = detector.analyze_text(cleaned_text)
                fresh_rep['id'] = report_id
                fresh_rep['title'] = report.get('title', '')
                fresh_rep['author'] = report.get('author', '')
                fresh_rep['status'] = report.get('status', 'مفحوص')
                fresh_rep['category'] = report.get('category', 'عام')
                fresh_rep['date'] = report.get('created_at', report.get('date', ''))
                fresh_rep['cheating'] = detect_cheating_manipulation(clean_txt)
                fresh_rep['ai_analysis'] = analyze_ai_generation(cleaned_text)
                fresh_rep['file_path'] = file_path

                db.save_report_db(
                    report_id=report_id,
                    title=fresh_rep['title'],
                    overall_pct=fresh_rep['overall_pct'],
                    copied_pct=fresh_rep['copied_pct'],
                    para_pct=fresh_rep['paraphrase_pct'],
                    report_dict=fresh_rep,
                    category=fresh_rep['category'],
                    status=fresh_rep['status'],
                    author=fresh_rep['author'],
                    file_path=file_path
                )
                return jsonify(fresh_rep)
        except Exception as e:
            logger.error(f"خطأ أثناء تحديث التقرير {report_id}: {e}")

    if 'page_limit_alert' not in report and 'sources' in report:
        exceeded = [s for s in report['sources'] if s.get('pages', 0) >= 5.0 or (s.get('words', 0) >= 1250)]
        report['page_limit_alert'] = {
            'has_limit_exceeded': len(exceeded) > 0,
            'max_allowed_pages': 5.0,
            'exceeded_sources': exceeded,
            'details': [
                f"تم اقتباس ما يعادل {s.get('pages', round(s.get('words', 0)/250, 1))} صفحة تقريباً من المرجع: «{s.get('title', '')}» للمؤلف ({s.get('author', 'غير محدد')})، متجاوزاً الحد الأقصى المسموح للاقتباس من مصدر واحد (5 صفحات)."
                for s in exceeded
            ]
        }

    return jsonify(report)


@app.route('/api/export_html/<report_id>', methods=['GET'])
def export_html(report_id):
    """تصدير التقرير كملف HTML للتحميل."""
    report = db.get_report_db(report_id)
    if not report:
        return jsonify({'error': 'التقرير غير موجود'}), 404

    if 'page_limit_alert' not in report and 'sources' in report:
        exceeded = [s for s in report['sources'] if s.get('pages', 0) >= 5.0 or (s.get('words', 0) >= 1250)]
        report['page_limit_alert'] = {
            'has_limit_exceeded': len(exceeded) > 0,
            'max_allowed_pages': 5.0,
            'exceeded_sources': exceeded,
            'details': [
                f"تم اقتباس ما يعادل {s.get('pages', round(s.get('words', 0)/250, 1))} صفحة تقريباً من المرجع: «{s.get('title', '')}» للمؤلف ({s.get('author', 'غير محدد')})، متجاوزاً الحد الأقصى المسموح للاقتباس من مصدر واحد (5 صفحات)."
                for s in exceeded
            ]
        }

    from plagiarism_detector.gui.app import _generate_html_report
    html_content = _generate_html_report(report)

    response = Response(html_content, mimetype='text/html')
    response.headers['Content-Disposition'] = f'attachment; filename="report_{report_id}.html"'
    return response



if __name__ == '__main__':
    import sys, io
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    print("=" * 65)
    print("   خادم نظام كشف الاستلال العلمي (Waitress Production WSGI Server)")
    print("   يعمل محلياً بالكامل (100% Offline) على: http://localhost:5000")
    print("=" * 65)
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=5000, threads=16)
    except Exception as e:
        print(f"   تشغيل الخادم عبر Flask WSGI: {e}")
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)


