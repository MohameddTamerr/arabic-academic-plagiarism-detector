# -*- coding: utf-8 -*-
"""
Script to apply the enhanced Upload Research / New Scan UI to templates/index.html.
Preserves all tests, accessibility, functionality, and matches the approved mockup.
"""
from pathlib import Path

INDEX_PATH = Path('templates/index.html')

css_target = '''        /* ─── Upload Screen Styles ──────────────────────────────────── */
        .upload-dropzone {
            border: 1.5px dashed var(--border-subtle);
            border-radius: var(--radius-lg);
            background: #ffffff;
            padding: 24px 18px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 14px;
        }

        .upload-dropzone.drag-active {
            border-color: var(--primary-navy);
            background: #eff6ff;
        }

        .upload-dropzone:hover {
            border-color: var(--primary-navy);
            background: #f8fafc;
        }'''

css_replacement = '''        /* ─── Upload Screen Styles ──────────────────────────────────── */
        #view-upload .content-constrained {
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
        }

        .new-scan-banner {
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 16px;
            margin-bottom: 18px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
            flex-wrap: wrap;
        }

        .banner-title-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .banner-info-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            color: #2563eb;
        }

        .banner-title {
            font-size: 17px;
            font-weight: 800;
            color: var(--primary-navy);
            margin: 0;
        }

        .banner-subtitle {
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 500;
        }

        .upload-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .upload-header-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            font-weight: 700;
            color: var(--primary-navy);
        }

        .upload-dropzone {
            border: 2px dashed #93c5fd;
            border-radius: 12px;
            background: #f8fafc;
            padding: 34px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-bottom: 16px;
        }

        .upload-dropzone.drag-active {
            border-color: #2563eb;
            background: #eff6ff;
            box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1);
        }

        .upload-dropzone:hover {
            border-color: #2563eb;
            background: #f1f5f9;
        }

        .selected-file-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 9px 14px;
            transition: all 0.15s ease;
        }

        .selected-file-row:hover {
            border-color: #cbd5e1;
            background: #f8fafc;
        }

        .selected-file-right {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
            flex: 1;
        }

        .file-check-circle {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #16a34a;
            flex-shrink: 0;
        }

        .file-type-badge {
            font-size: 10.5px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 4px;
            text-transform: uppercase;
            flex-shrink: 0;
        }

        .file-type-badge.badge-pdf {
            background: #fee2e2;
            color: #dc2626;
        }

        .file-type-badge.badge-word {
            background: #dbeafe;
            color: #2563eb;
        }

        .file-type-badge.badge-txt {
            background: #f1f5f9;
            color: #475569;
        }

        .selected-file-name {
            font-size: 13.5px;
            font-weight: 700;
            color: var(--primary-navy);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .selected-file-left {
            display: flex;
            align-items: center;
            gap: 14px;
            flex-shrink: 0;
        }

        .selected-file-size {
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .btn-remove-file {
            background: transparent;
            border: none;
            color: #ef4444;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 4px;
            border-radius: 6px;
            transition: all 0.15s ease;
        }

        .btn-remove-file:hover {
            background: #fee2e2;
            color: #b91c1c;
        }

        .ocr-mode-card {
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px 14px;
            cursor: pointer;
            transition: all 0.15s ease;
            user-select: none;
            text-align: right;
            width: 100%;
            display: block;
            outline: none;
        }

        .ocr-mode-card:hover {
            border-color: #93c5fd;
            background: #f8fafc;
        }

        .ocr-mode-card.active {
            background: #eff6ff !important;
            border: 1.5px solid #2563eb !important;
            box-shadow: 0 0 0 1px #2563eb !important;
        }

        .ocr-mode-title {
            font-size: 13px;
            font-weight: 700;
            color: var(--primary-navy);
        }

        .ocr-mode-desc {
            font-size: 11px;
            color: var(--text-muted);
            line-height: 1.4;
            margin-top: 3px;
        }

        .ocr-radio-circle {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 1.5px solid #94a3b8;
            background: white;
        }

        .ocr-mode-card.active .ocr-radio-circle {
            border-color: #2563eb;
        }

        .ocr-radio-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: transparent;
        }

        .ocr-mode-card.active .ocr-radio-dot {
            background: #2563eb;
        }

        .ai-research-card {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 10px;
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .ai-research-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
            flex-wrap: wrap;
            gap: 8px;
        }

        .ai-research-title-group {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12.5px;
            font-weight: 700;
            color: var(--primary-navy);
        }

        .ai-research-toggle-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .ai-research-toggle-label {
            font-size: 11.5px;
            font-weight: 700;
            color: #1e40af;
        }

        .ai-research-disclaimer {
            font-size: 10.5px;
            color: #475569;
            line-height: 1.4;
            display: flex;
            align-items: flex-start;
            gap: 5px;
        }

        .switch-toggle {
            position: relative;
            display: inline-block;
            width: 36px;
            height: 20px;
            flex-shrink: 0;
        }

        .switch-toggle input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider-toggle {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #cbd5e1;
            transition: 0.25s;
            border-radius: 20px;
        }

        .slider-toggle:before {
            position: absolute;
            content: "";
            height: 14px;
            width: 14px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: 0.25s;
            border-radius: 50%;
        }

        .switch-toggle input:checked + .slider-toggle {
            background-color: #2563eb;
        }

        .switch-toggle input:checked + .slider-toggle:before {
            transform: translateX(16px);
        }

        .upload-action-footer {
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }'''

html_start = '            <!-- ================= VIEW 2: UPLOAD (MULTI-PDF) ================= -->'
html_end = '            <!-- ================= VIEW INITIAL REVIEW: PENDING ADMIN REVIEW QUEUE ================= -->'

html_replacement = '''            <!-- ================= VIEW 2: UPLOAD (MULTI-PDF) ================= -->
            <!-- ================= VIEW 2: UPLOAD (MULTI-PDF / THESIS / BATCH) ================= -->
            <section id="view-upload" class="view-section"><div class="content-constrained">
                <!-- Top Banner: New Scan -->
                <div class="new-scan-banner">
                    <div class="banner-title-group">
                        <span class="banner-info-icon">
                            <svg class="nav-icon-svg" style="width:20px; height:20px; stroke:#2563eb;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                        </span>
                        <h2 class="banner-title">فحص جديد</h2>
                    </div>
                    <div class="banner-subtitle">
                        يمكن رفع بحث واحد أو عدة أبحاث مستقلة أو تجميع ملفات رسالة واحدة للفحص الأكاديمي الشامل.
                    </div>
                </div>
                
                <div class="card">
                    <!-- Default Upload Header with Secondary Thesis Action -->
                    <div class="upload-card-header">
                        <div class="upload-header-title">
                            <svg class="nav-icon-svg" style="width:18px; height:18px; stroke:var(--primary-navy);" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                            <span id="upload-main-heading">رفع المستندات والأبحاث للفحص الأكاديمي</span>
                        </div>
                        <!-- Secondary Optional Action for Multi-file Thesis -->
                        <div>
                            <button type="button" id="toggle-thesis-mode-btn" class="btn-secondary" onclick="toggleThesisMode()" style="padding: 6px 12px; font-size: 12px; border-radius: 6px; display: flex; align-items: center; gap: 6px;">
                                <svg class="nav-icon-svg" style="width:14px; height:14px; stroke:currentColor;" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
                                <span id="toggle-thesis-mode-text">تجميع عدة ملفات كرسالة واحدة</span>
                            </button>
                        </div>
                    </div>

                    <input type="file" id="file-input" style="display: none;" onchange="handleFileSelect(event)" accept=".pdf,.docx,.txt" multiple>
                    
                    <div class="upload-dropzone" id="dropzone-area" onclick="document.getElementById('file-input').click()">
                        <div style="margin-bottom: 12px;">
                            <svg class="nav-icon-svg" style="width:52px; height:52px; stroke:var(--primary-navy);" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"></path><polyline points="16 16 12 12 8 16"></polyline><line x1="12" y1="12" x2="12" y2="21"></line></svg>
                        </div>
                        <h3 id="dropzone-title" style="font-size: 17px; font-weight: 700; color: var(--primary-navy); margin-bottom: 6px;">اسحب ملفات الأبحاث هنا أو انقر لاختيار ملف أو عدة ملفات</h3>
                        <p id="dropzone-subtitle" style="color: var(--text-muted); font-size: 12.5px;">يدعم رفع بحث واحد أو عدة أبحاث بصيغ: PDF / Word / TXT (لفحص كل ملف كمستند مستقل تلقائياً)</p>
                    </div>

                    <!-- ─── THESIS METADATA (Asked ONLY ONCE in Thesis Mode) ─── -->
                    <div id="thesis-metadata-container" style="display: none; margin-top: 20px; padding: 16px; background: #f8fafc; border: 1px solid var(--border-color); border-radius: 10px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: var(--primary-navy); margin-bottom: 12px;">بيانات الرسالة / البحث الموحد:</h4>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                            <div>
                                <label style="font-size: 12px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 4px;">عنوان البحث / الرسالة <span style="color:#dc2626;">*</span>:</label>
                                <input type="text" id="thesis-title" placeholder="أدخل عنوان الرسالة أو الأطروحة..." style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px;">
                            </div>
                            <div>
                                <label style="font-size: 12px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 4px;">اسم الباحث <span style="color:#dc2626;">*</span>:</label>
                                <input type="text" id="thesis-author" placeholder="أدخل اسم الباحث..." style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px;">
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                            <div>
                                <label style="font-size: 12px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 4px;">التخصص:</label>
                                <input type="text" id="thesis-spec" placeholder="مثال: العلوم الجنائية، القانون العام..." style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px;">
                            </div>
                            <div>
                                <label style="font-size: 12px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 4px;">الدرجة / النوع:</label>
                                <select id="thesis-degree" style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px; background: white;">
                                    <option value="ماجستير">رسالة ماجستير</option>
                                    <option value="دكتوراه">أطروحة دكتوراه</option>
                                    <option value="دبلوم">بحث دبلوم</option>
                                    <option value="ترقية">بحث ترقية علمية</option>
                                    <option value="عام">بحث عام</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    <!-- ─── THESIS ORDERED FILES LIST (with Up/Down/Delete) ─── -->
                    <div id="thesis-files-list" style="display: none; margin-top: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h4 style="font-size: 14px; font-weight: 700; color: var(--primary-navy);">ملفات الرسالة المرتبة (أبواب / فصول / ملاحق):</h4>
                            <span style="font-size: 12px; color: var(--text-muted);">استخدم أزرار ▲ و ▼ لضبط ترتيب الأبواب</span>
                        </div>
                        <div id="thesis-items-container" style="display: flex; flex-direction: column; gap: 8px;">
                            <!-- Dynamic Ordered Files with Up/Down/Delete controls -->
                        </div>
                    </div>

                    <!-- ─── BATCH INDEPENDENT FILES LIST ─── -->
                    <div id="batch-files-list" style="display: none; margin-top: 18px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                            <svg class="nav-icon-svg" style="width:16px; height:16px; stroke:var(--primary-navy);" viewBox="0 0 24 24"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                            <h4 id="batch-files-count-heading" style="font-size: 14px; font-weight: 700; color: var(--primary-navy); margin: 0;">الملفات المختارة (0)</h4>
                        </div>
                        <div id="batch-items-container" style="display: flex; flex-direction: column; gap: 8px;">
                            <!-- Dynamic File Cards matching mockup -->
                        </div>
                    </div>

                    <!-- Single Raw Text Input (Preserved for quick single text) -->
                    <div id="raw-text-container" style="margin-top: 20px;">
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
                            <svg class="nav-icon-svg" style="width:14px; height:14px; stroke:var(--text-secondary);" viewBox="0 0 24 24"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                            <h4 style="font-size: 13.5px; font-weight: 700; color: var(--text-secondary); margin: 0;">أو ادخل نص البحث مباشرة (للفحص الفردي السريع):</h4>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 10px;">
                            <input type="text" id="raw-single-title" placeholder="عنوان البحث (مطلوب عند الفحص النصي)" style="padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border-color); font-size: 13.5px; outline: none; background: white;">
                            <input type="text" id="raw-single-author" placeholder="اسم الباحث / صاحب البحث" style="padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border-color); font-size: 13.5px; outline: none; background: white;">
                        </div>
                        <textarea id="raw-text-input" rows="3" style="width: 100%; padding: 12px; border-radius: 8px; border: 1px solid var(--border-color); font-size: 13.5px; outline: none; resize: vertical;" placeholder="الصق نص البحث هنا..."></textarea>
                    </div>

                    <!-- Settings Row: OCR Precision Options + AI Research Mode Card -->
                    <div style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <!-- Right Column (OCR Mode Selection) -->
                        <div>
                            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
                                <svg class="nav-icon-svg" style="width:16px; height:16px; stroke:var(--primary-navy);" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1.81-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                                <span style="font-size: 13px; font-weight: 700; color: var(--text-dark);">نمط معالجة المستندات (OCR):</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                <!-- Card 1: Accurate (default active) -->
                                <button type="button" id="ocr-btn-accurate" class="ocr-mode-card active" onclick="setOcrModeSelection('accurate')" style="text-align: right; width: 100%;">
                                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                                        <span class="ocr-mode-title">دقة قصوى (افتراضي)</span>
                                        <span class="ocr-radio-circle"><span class="ocr-radio-dot"></span></span>
                                    </div>
                                    <div class="ocr-mode-desc">مناسب للملفات المصنوعة ضوئياً أو ذات الجودة الضعيفة</div>
                                </button>
                                <!-- Card 2: Fast -->
                                <button type="button" id="ocr-btn-fast" class="ocr-mode-card" onclick="setOcrModeSelection('fast')" style="text-align: right; width: 100%;">
                                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                                        <span class="ocr-mode-title">فحص سريع</span>
                                        <span class="ocr-radio-circle"><span class="ocr-radio-dot"></span></span>
                                    </div>
                                    <div class="ocr-mode-desc">مناسب للملفات الرقمية الواضحة</div>
                                </button>
                            </div>
                            <span id="ocr-mode-desc-text" style="display: none;">أعلى دقة للتعرف على النصوص الأكاديمية والممسوحة ضوئياً</span>
                        </div>

                        <!-- Left Column (AI Research Mode Card) -->
                        <div id="ai-research-upload-card" class="ai-research-card">
                            <div class="ai-research-header">
                                <div class="ai-research-title-group">
                                    <svg class="nav-icon-svg" style="width:16px; height:16px; stroke:#2563eb;" viewBox="0 0 24 24"><path d="M10 2v7.31L4.69 18.5A2 2 0 0 0 6.4 21.5h11.2a2 2 0 0 0 1.71-3L14 9.31V2"></path><line x1="8.5" y1="2" x2="15.5" y2="2"></line><line x1="14" y1="9.3" x2="10" y2="9.3"></line></svg>
                                    <span>فحص تجريبي للذكاء الاصطناعي (Research Mode)</span>
                                </div>
                                <div class="ai-research-toggle-group">
                                    <label class="switch-toggle">
                                        <input type="checkbox" id="toggle-ai-research" checked onchange="toggleAiResearchMode(this.checked)">
                                        <span class="slider-toggle"></span>
                                    </label>
                                    <span id="ai-toggle-status-label" class="ai-research-toggle-label">مُفعّل (للمستخدمين المصرح لهم فقط)</span>
                                </div>
                            </div>
                            <div class="ai-research-disclaimer">
                                <svg class="nav-icon-svg" style="width:14px; height:14px; stroke:#3b82f6; flex-shrink:0; margin-top:2px;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                                <span>ملاحظة: نتائج كشف الكتابة بالذكاء الاصطناعي استرشادية وتجريبية وليست دليلاً قاطعاً على مصدر النص أو ارتكاب مخالفة أكاديمية</span>
                            </div>
                        </div>
                    </div>

                    <!-- Scan Mode Summary & One Primary Action Button -->
                    <div class="upload-action-footer">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; color: var(--text-muted);">
                                <svg class="nav-icon-svg" style="width: 20px; height: 20px; stroke: #64748b;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                            </span>
                            <div style="font-size: 12px; line-height: 1.4;">
                                <div style="font-weight: 700; color: var(--text-dark);">سيتم فحص الملفات باستخدام:</div>
                                <div style="color: var(--text-muted);">كشف الاستلال (اللفظي والدلالي) + التحليل التجريبي للذكاء الاصطناعي (إن كان مفعلاً)</div>
                            </div>
                        </div>

                        <!-- One Clear Primary Analyze Action -->
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button class="btn-primary" id="btn-start-analysis" onclick="startAnalysis()" style="font-size: 14px; font-weight: 800; padding: 10px 24px; border-radius: 8px; display: inline-flex; align-items: center; gap: 8px; box-shadow: 0 2px 6px rgba(15,43,92,0.2);">
                                <svg class="nav-icon-svg" style="width:14px; height:14px; stroke:white; fill:white;" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                                <span id="btn-start-analysis-text">بدء فحص البحث</span>
                            </button>
                            <!-- Retain btn-start-fast-analysis hidden for backwards compatibility -->
                            <button id="btn-start-fast-analysis" hidden onclick="startAnalysis('fast')">
                                <svg class="nav-icon-svg" style="width:15px; height:15px;" viewBox="0 0 24 24"><path d="M13 2 3 14h8l-1 8 10-12h-8l1-8z"></path></svg>
                                <span>فحص سريع</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div></section>'''

js_target_old = '''        function setUploadMode(mode) {
            currentUploadMode = mode;
            const toggleBtn = document.getElementById('toggle-thesis-mode-btn');
            const toggleText = document.getElementById('toggle-thesis-mode-text');
            const mainHeading = document.getElementById('upload-main-heading');
            const dropTitle = document.getElementById('dropzone-title');
            const dropSub = document.getElementById('dropzone-subtitle');
            const thesisMeta = document.getElementById('thesis-metadata-container');
            const thesisList = document.getElementById('thesis-files-list');
            const batchList = document.getElementById('batch-files-list');
            const btnText = document.getElementById('btn-start-analysis-text');
            const rawContainer = document.getElementById('raw-text-container');

            if (mode === 'thesis') {
                if (toggleText) toggleText.innerText = 'العودة للفحص العادي (بحث فردي / متعدد)';
                if (toggleBtn) toggleBtn.className = 'btn-secondary';
                if (mainHeading) mainHeading.innerText = 'تجميع عدة ملفات لأطروحة / رسالة علمية واحدة';
                if (dropTitle) dropTitle.innerText = 'اسحب ملفات الرسالة (الأبواب والفصول) هنا أو انقر للاختيار';
                if (dropSub) dropSub.innerText = 'أضف جميع ملفات الرسالة مع إمكانية ترتيب الأبواب قبل الفحص';
                if (thesisMeta) thesisMeta.style.display = 'block';
                if (thesisList) thesisList.style.display = thesisFiles.length > 0 ? 'block' : 'none';
                if (batchList) batchList.style.display = 'none';
                if (btnText) btnText.innerText = 'تجميع الملفات وبدء الفحص';
                if (rawContainer) rawContainer.style.display = 'none';
            } else {
                if (toggleText) toggleText.innerText = 'تجميع عدة ملفات كرسالة واحدة';
                if (toggleBtn) toggleBtn.className = 'btn-secondary';
                if (mainHeading) mainHeading.innerText = 'رفع المستندات والأبحاث للفحص الأكاديمي';
                if (dropTitle) dropTitle.innerText = 'اسحب ملفات الأبحاث هنا أو انقر لاختيار ملف أو عدة ملفات';
                if (dropSub) dropSub.innerText = 'يدعم رفع بحث واحد أو عدة أبحاث بصيغ PDF / Word / TXT (يُفحص كل ملف كبحث مستقل تلقائياً)';
                if (thesisMeta) thesisMeta.style.display = 'none';
                if (thesisList) thesisList.style.display = 'none';
                if (batchList) batchList.style.display = batchFiles.length > 0 ? 'block' : 'none';
                if (btnText) btnText.innerText = batchFiles.length > 1 ? 'بدء فحص جميع الأبحاث المختارة' : 'بدء فحص البحث';
                if (rawContainer) rawContainer.style.display = 'block';
            }
        }'''

js_replacement_new = '''        let isAiResearchEnabled = true;

        function toggleAiResearchMode(enabled) {
            isAiResearchEnabled = Boolean(enabled);
            const lbl = document.getElementById('ai-toggle-status-label');
            if (lbl) {
                lbl.innerText = isAiResearchEnabled ? 'مُفعّل (للمستخدمين المصرح لهم فقط)' : 'مُعطّل (استثناء فحص AI)';
            }
        }

        function setUploadMode(mode) {
            currentUploadMode = mode;
            const toggleBtn = document.getElementById('toggle-thesis-mode-btn');
            const toggleText = document.getElementById('toggle-thesis-mode-text');
            const mainHeading = document.getElementById('upload-main-heading');
            const dropTitle = document.getElementById('dropzone-title');
            const dropSub = document.getElementById('dropzone-subtitle');
            const thesisMeta = document.getElementById('thesis-metadata-container');
            const thesisList = document.getElementById('thesis-files-list');
            const batchList = document.getElementById('batch-files-list');
            const btnText = document.getElementById('btn-start-analysis-text');
            const rawContainer = document.getElementById('raw-text-container');

            if (mode === 'thesis') {
                if (toggleText) toggleText.innerText = 'العودة للفحص العادي (بحث فردي / متعدد)';
                if (toggleBtn) toggleBtn.className = 'btn-secondary';
                if (mainHeading) mainHeading.innerText = 'تجميع عدة ملفات لأطروحة / رسالة علمية واحدة';
                if (dropTitle) dropTitle.innerText = 'اسحب ملفات الرسالة (الأبواب والفصول) هنا أو انقر للاختيار';
                if (dropSub) dropSub.innerText = 'أضف جميع ملفات الرسالة مع إمكانية ترتيب الأبواب قبل الفحص';
                if (thesisMeta) thesisMeta.style.display = 'block';
                if (thesisList) thesisList.style.display = thesisFiles.length > 0 ? 'block' : 'none';
                if (batchList) batchList.style.display = 'none';
                if (btnText) btnText.innerText = 'تجميع الملفات وبدء الفحص';
                if (rawContainer) rawContainer.style.display = 'none';
            } else {
                if (toggleText) toggleText.innerText = 'تجميع عدة ملفات كرسالة واحدة';
                if (toggleBtn) toggleBtn.className = 'btn-secondary';
                if (mainHeading) mainHeading.innerText = 'رفع المستندات والأبحاث للفحص الأكاديمي';
                if (dropTitle) dropTitle.innerText = 'اسحب ملفات الأبحاث هنا أو انقر لاختيار ملف أو عدة ملفات';
                if (dropSub) dropSub.innerText = 'يدعم رفع بحث واحد أو عدة أبحاث بصيغ: PDF / Word / TXT (لفحص كل ملف كمستند مستقل تلقائياً)';
                if (thesisMeta) thesisMeta.style.display = 'none';
                if (thesisList) thesisList.style.display = 'none';
                if (batchList) batchList.style.display = batchFiles.length > 0 ? 'block' : 'none';
                if (btnText) btnText.innerText = batchFiles.length > 0 ? `بدء فحص الملفات (${batchFiles.length})` : 'بدء فحص البحث';
                if (rawContainer) rawContainer.style.display = 'block';
            }
        }'''

# JS renderBatchFiles replacement
js_batch_old = '''        function renderBatchFiles() {
            const container = document.getElementById('batch-items-container');
            const listWrapper = document.getElementById('batch-files-list');
            if (!container || !listWrapper) return;

            if (batchFiles.length === 0) {
                listWrapper.style.display = 'none';
                return;
            }
            listWrapper.style.display = 'block';

            let html = '';
            batchFiles.forEach((item, idx) => {
                const ext = item.file.name.split('.').pop().toUpperCase();
                const sizeMB = (item.file.size / (1024 * 1024)).toFixed(2);

                html += `
                    <div style="background: #ffffff; border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                                <span style="display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 4px; background: #e0f2fe; color: #0284c7; font-size: 11.5px; font-weight: 700;">${idx + 1}</span>
                                <span style="font-weight: 700; font-size: 13.5px; color: var(--primary-navy);">${item.file.name}</span>
                                <span style="font-size: 11.5px; color: var(--text-muted); background: #f1f5f9; padding: 1px 6px; border-radius: 4px;">${ext}</span>
                                <span style="font-size: 11.5px; color: var(--text-muted);">(${sizeMB} MB)</span>
                            </div>
                            <button type="button" class="btn-danger" onclick="removeBatchFile(${idx})" style="padding: 2px 8px; font-size: 11px; border-radius: 6px;" title="إزالة">
                                ✕
                            </button>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div>
                                <label style="font-size: 11.5px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 3px;">عنوان البحث <span style="color:#dc2626;">*</span>:</label>
                                <input type="text" id="batch-title-${idx}" value="${item.title}" oninput="batchFiles[${idx}].title = this.value" placeholder="ادخل عنوان البحث..." style="width: 100%; padding: 7px 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 12.5px;">
                            </div>
                            <div>
                                <label style="font-size: 11.5px; font-weight: 700; color: var(--text-dark); display: block; margin-bottom: 3px;">اسم الباحث / صاحب البحث <span style="color:#dc2626;">*</span>:</label>
                                <input type="text" id="batch-author-${idx}" value="${item.author}" oninput="batchFiles[${idx}].author = this.value" placeholder="ادخل اسم الباحث..." style="width: 100%; padding: 7px 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 12.5px;">
                            </div>
                        </div>
                    </div>
                `;
            });
            container.innerHTML = html;
        }'''

js_batch_new = '''        function renderBatchFiles() {
            const container = document.getElementById('batch-items-container');
            const listWrapper = document.getElementById('batch-files-list');
            const countHeading = document.getElementById('batch-files-count-heading');
            const btnText = document.getElementById('btn-start-analysis-text');
            if (!container || !listWrapper) return;

            if (batchFiles.length === 0) {
                listWrapper.style.display = 'none';
                if (btnText && currentUploadMode === 'batch') btnText.innerText = 'بدء فحص البحث';
                return;
            }
            listWrapper.style.display = 'block';
            if (countHeading) countHeading.innerText = `الملفات المختارة (${batchFiles.length})`;
            if (btnText && currentUploadMode === 'batch') {
                btnText.innerText = `بدء فحص الملفات (${batchFiles.length})`;
            }

            let html = '';
            batchFiles.forEach((item, idx) => {
                const ext = item.file.name.split('.').pop().toLowerCase();
                const extBadge = ext.toUpperCase();
                const badgeClass = ext === 'pdf' ? 'badge-pdf' : (ext === 'docx' || ext === 'doc' ? 'badge-word' : 'badge-txt');
                const sizeMB = (item.file.size / (1024 * 1024)).toFixed(2);
                const safeName = (item.file.name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

                html += `
                    <div class="selected-file-row">
                        <div class="selected-file-right">
                            <span class="file-check-circle" title="ملف صالح للفحص">
                                <svg viewBox="0 0 24 24" style="width: 12px; height: 12px; stroke: white; stroke-width: 3; fill: none;"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            </span>
                            <span class="file-type-badge ${badgeClass}">${extBadge}</span>
                            <span class="selected-file-name" title="${safeName}">${safeName}</span>
                        </div>
                        <div class="selected-file-left">
                            <span class="selected-file-size">${sizeMB} MB</span>
                            <button type="button" class="btn-remove-file" onclick="removeBatchFile(${idx})" title="حذف الملف">
                                <svg viewBox="0 0 24 24" style="width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            </button>
                        </div>
                    </div>
                `;
            });
            container.innerHTML = html;
        }'''

# JS setOcrModeSelection replacement
js_ocr_old = '''        function setOcrModeSelection(mode) {
            currentOcrModeSelection = mode === 'fast' ? 'fast' : 'accurate';
            const btnAccurate = document.getElementById('ocr-btn-accurate');
            const btnFast = document.getElementById('ocr-btn-fast');
            const desc = document.getElementById('ocr-mode-desc-text');
            if (currentOcrModeSelection === 'fast') {
                if (btnAccurate) { btnAccurate.style.background = 'transparent'; btnAccurate.style.color = '#64748b'; btnAccurate.style.boxShadow = 'none'; btnAccurate.classList.remove('active'); }
                if (btnFast) { btnFast.style.background = '#ffffff'; btnFast.style.color = 'var(--primary-navy)'; btnFast.style.boxShadow = '0 1px 2px rgba(0,0,0,0.06)'; btnFast.classList.add('active'); }
                if (desc) desc.innerText = 'فحص سريع يقلل زمن OCR للملفات الممسوحة ضوئياً (مناسب لبيئة 8GB RAM)';
            } else {
                if (btnAccurate) { btnAccurate.style.background = '#ffffff'; btnAccurate.style.color = 'var(--primary-navy)'; btnAccurate.style.boxShadow = '0 1px 2px rgba(0,0,0,0.06)'; btnAccurate.classList.add('active'); }
                if (btnFast) { btnFast.style.background = 'transparent'; btnFast.style.color = '#64748b'; btnFast.style.boxShadow = 'none'; btnFast.classList.remove('active'); }
                if (desc) desc.innerText = 'أعلى دقة للتعرف على النصوص الأكاديمية والممسوحة ضوئياً';
            }
        }'''

js_ocr_new = '''        function setOcrModeSelection(mode) {
            currentOcrModeSelection = mode === 'fast' ? 'fast' : 'accurate';
            const btnAccurate = document.getElementById('ocr-btn-accurate');
            const btnFast = document.getElementById('ocr-btn-fast');
            const desc = document.getElementById('ocr-mode-desc-text');
            if (currentOcrModeSelection === 'fast') {
                if (btnAccurate) { btnAccurate.classList.remove('active'); }
                if (btnFast) { btnFast.classList.add('active'); }
                if (desc) desc.innerText = 'فحص سريع يقلل زمن OCR للملفات الممسوحة ضوئياً (مناسب لبيئة 8GB RAM)';
            } else {
                if (btnAccurate) { btnAccurate.classList.add('active'); }
                if (btnFast) { btnFast.classList.remove('active'); }
                if (desc) desc.innerText = 'أعلى دقة للتعرف على النصوص الأكاديمية والممسوحة ضوئياً';
            }
        }'''

# JS submitAnalysis updates (pass enable_ai_research, handle batch author default)
js_submit_old = '''            // ─── 1. THESIS MULTI-FILE SCAN ──────────────────────────────────────────
            if (currentUploadMode === 'thesis') {
                if (thesisFiles.length === 0) {
                    showToast('الرجاء اختيار ملفات الرسالة (أبواب / فصول) أولاً.', 'warning');
                    return;
                }
                const title = document.getElementById('thesis-title').value.trim();
                const author = document.getElementById('thesis-author').value.trim();
                const spec = document.getElementById('thesis-spec').value.trim();
                const degree = document.getElementById('thesis-degree').value;

                if (!title) {
                    showToast('يرجى إدخال عنوان الرسالة / الأطروحة.', 'warning');
                    document.getElementById('thesis-title').focus();
                    return;
                }
                if (!author) {
                    showToast('يرجى إدخال اسم الباحث صاحب الرسالة.', 'warning');
                    document.getElementById('thesis-author').focus();
                    return;
                }

                showToast(`جاري رفع ملفات الرسالة وبدء ${scanModeLabel}...`, 'info');

                const formData = new FormData();
                thesisFiles.forEach((file, i) => {
                    formData.append('files[]', file);
                    formData.append('orders[]', i);
                });
                formData.append('title', title);
                formData.append('author', author);
                formData.append('specialization', spec);
                formData.append('degree_type', degree);
                formData.append('created_by', currentUserName);
                formData.append('ocr_mode', ocrMode);'''

js_submit_new = '''            // ─── 1. THESIS MULTI-FILE SCAN ──────────────────────────────────────────
            if (currentUploadMode === 'thesis') {
                if (thesisFiles.length === 0) {
                    showToast('الرجاء اختيار ملفات الرسالة (أبواب / فصول) أولاً.', 'warning');
                    return;
                }
                const title = document.getElementById('thesis-title').value.trim();
                const author = document.getElementById('thesis-author').value.trim();
                const spec = document.getElementById('thesis-spec').value.trim();
                const degree = document.getElementById('thesis-degree').value;

                if (!title) {
                    showToast('يرجى إدخال عنوان الرسالة / الأطروحة.', 'warning');
                    document.getElementById('thesis-title').focus();
                    return;
                }
                if (!author) {
                    showToast('يرجى إدخال اسم الباحث صاحب الرسالة.', 'warning');
                    document.getElementById('thesis-author').focus();
                    return;
                }

                showToast(`جاري رفع ملفات الرسالة وبدء ${scanModeLabel}...`, 'info');

                const formData = new FormData();
                thesisFiles.forEach((file, i) => {
                    formData.append('files[]', file);
                    formData.append('orders[]', i);
                });
                formData.append('title', title);
                formData.append('author', author);
                formData.append('specialization', spec);
                formData.append('degree_type', degree);
                formData.append('created_by', currentUserName);
                formData.append('ocr_mode', ocrMode);
                formData.append('enable_ai_research', isAiResearchEnabled ? '1' : '0');'''

js_batch_sub_old = '''            // ─── 2. BATCH INDEPENDENT MULTI-RESEARCH SCAN ───────────────────────────
            if (currentUploadMode === 'batch' && batchFiles.length > 0) {
                for (let i = 0; i < batchFiles.length; i++) {
                    const t = (batchFiles[i].title || '').trim();
                    const a = (batchFiles[i].author || '').trim();
                    if (!t || !a) {
                        showToast(`يرجى استكمال عنوان البحث واسم الباحث للبحث رقم ${i + 1}`, 'warning');
                        const el = document.getElementById(`batch-title-${i}`) || document.getElementById(`batch-author-${i}`);
                        if (el) el.focus();
                        return;
                    }
                }

                showToast(`جاري إطلاق ${scanModeLabel} لدفعة من ${batchFiles.length} أبحاث...`, 'info');

                const formData = new FormData();
                batchFiles.forEach(item => {
                    formData.append('files[]', item.file);
                    formData.append('titles[]', item.title.trim());
                    formData.append('authors[]', item.author.trim());
                });
                formData.append('created_by', currentUserName);
                formData.append('label', `دفعة ${batchFiles.length} أبحاث`);
                formData.append('ocr_mode', ocrMode);'''

js_batch_sub_new = '''            // ─── 2. BATCH INDEPENDENT MULTI-RESEARCH SCAN ───────────────────────────
            if (currentUploadMode === 'batch' && batchFiles.length > 0) {
                const globalAuthor = (document.getElementById('raw-single-author') ? document.getElementById('raw-single-author').value.trim() : '') || currentUserName;
                const globalTitle = (document.getElementById('raw-single-title') ? document.getElementById('raw-single-title').value.trim() : '');

                for (let i = 0; i < batchFiles.length; i++) {
                    if (!batchFiles[i].title) {
                        batchFiles[i].title = (batchFiles.length === 1 && globalTitle) ? globalTitle : batchFiles[i].file.name.replace(/\\.[^/.]+$/, '');
                    }
                    if (!batchFiles[i].author) {
                        batchFiles[i].author = globalAuthor;
                    }
                }

                showToast(`جاري إطلاق ${scanModeLabel} لدفعة من ${batchFiles.length} أبحاث...`, 'info');

                const formData = new FormData();
                batchFiles.forEach(item => {
                    formData.append('files[]', item.file);
                    formData.append('titles[]', item.title.trim());
                    formData.append('authors[]', item.author.trim());
                });
                formData.append('created_by', currentUserName);
                formData.append('label', `دفعة ${batchFiles.length} أبحاث`);
                formData.append('ocr_mode', ocrMode);
                formData.append('enable_ai_research', isAiResearchEnabled ? '1' : '0');'''

js_raw_sub_old = '''            const formData = new FormData();
            formData.append('text', rawText);
            formData.append('title', rawTitle);
            formData.append('author', rawAuthor || 'غير محدد');
            formData.append('ocr_mode', ocrMode);'''

js_raw_sub_new = '''            const formData = new FormData();
            formData.append('text', rawText);
            formData.append('title', rawTitle);
            formData.append('author', rawAuthor || 'غير محدد');
            formData.append('ocr_mode', ocrMode);
            formData.append('enable_ai_research', isAiResearchEnabled ? '1' : '0');'''

content = INDEX_PATH.read_text(encoding='utf-8')

assert css_target in content, 'CSS target not found'
content = content.replace(css_target, css_replacement)

start_idx = content.find(html_start)
end_idx = content.find(html_end)
assert start_idx != -1 and end_idx != -1, 'HTML view-upload section markers not found'
content = content[:start_idx] + html_replacement + '\n\n' + content[end_idx:]

assert js_target_old in content, 'js_target_old not found'
content = content.replace(js_target_old, js_replacement_new)

assert js_batch_old in content, 'js_batch_old not found'
content = content.replace(js_batch_old, js_batch_new)

assert js_ocr_old in content, 'js_ocr_old not found'
content = content.replace(js_ocr_old, js_ocr_new)

assert js_submit_old in content, 'js_submit_old not found'
content = content.replace(js_submit_old, js_submit_new)

assert js_batch_sub_old in content, 'js_batch_sub_old not found'
content = content.replace(js_batch_sub_old, js_batch_sub_new)

assert js_raw_sub_old in content, 'js_raw_sub_old not found'
content = content.replace(js_raw_sub_old, js_raw_sub_new)

INDEX_PATH.write_text(content, encoding='utf-8')
print('Successfully updated templates/index.html')
