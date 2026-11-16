# -*- coding: utf-8 -*-
"""
Safely enhance the Home Dashboard in templates/index.html
matching media_1794853811169_9e477511.jpg
"""
import shutil
import re

INDEX_PATH = 'templates/index.html'
BACKUP_PATH = 'templates/index.html.bak_20261116_pre_home_dashboard'

# 1. Create Backup
shutil.copyfile(INDEX_PATH, BACKUP_PATH)
print(f"Created backup at {BACKUP_PATH}")

with open(INDEX_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 2. CSS Enhancement
CSS_TARGET = "        /* ─── Upload Screen Styles ──────────────────────────────────── */"

DASHBOARD_CSS = """        /* ─── Home Dashboard Enhanced Styles (Mockup Reference) ────── */
        .dash-banner {
            background: #ffffff;
            border: 1px solid var(--border-color, #e2e8f0);
            border-radius: 12px;
            padding: 16px 24px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            min-height: 80px;
        }

        .dash-banner-right {
            display: flex;
            align-items: center;
            gap: 14px;
            position: relative;
            z-index: 2;
        }

        .dash-banner-icon {
            width: 44px;
            height: 44px;
            border-radius: 10px;
            background: #1e3a8a;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(30, 58, 138, 0.25);
        }

        .dash-banner-title {
            font-size: 22px;
            font-weight: 800;
            color: #0f172a;
            margin: 0 0 4px 0;
            letter-spacing: -0.3px;
            line-height: 1.2;
        }

        .dash-banner-subtitle {
            font-size: 13.5px;
            color: #64748b;
            margin: 0;
            font-weight: 500;
        }

        .dash-banner-bg {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 340px;
            background-image: url('/static/login.jpg');
            background-size: cover;
            background-position: center left;
            opacity: 0.22;
            mask-image: linear-gradient(to right, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%);
            -webkit-mask-image: linear-gradient(to right, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%);
            pointer-events: none;
            z-index: 1;
        }

        .dash-kpis-container {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }

        @media (max-width: 960px) {
            .dash-kpis-container {
                grid-template-columns: 1fr;
            }
        }

        .dash-kpi-card {
            background: #ffffff;
            border: 1px solid var(--border-color, #e2e8f0);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            cursor: pointer;
            position: relative;
        }

        .dash-kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
        }

        .dash-kpi-card.accent-green {
            border-top: 3.5px solid #10b981;
        }

        .dash-kpi-card.accent-blue {
            border-top: 3.5px solid #2563eb;
        }

        .dash-kpi-info {
            display: flex;
            flex-direction: column;
        }

        .dash-kpi-header {
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin-bottom: 4px;
        }

        .dash-kpi-title {
            font-size: 15px;
            font-weight: 700;
            color: #1e293b;
        }

        .dash-kpi-number {
            font-size: 32px;
            font-weight: 800;
            line-height: 1;
            color: #0f172a;
            font-feature-settings: "tnum";
        }

        .dash-kpi-number.green {
            color: #10b981;
        }

        .dash-kpi-number.blue {
            color: #2563eb;
        }

        .dash-kpi-desc {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
        }

        .dash-kpi-icon {
            width: 46px;
            height: 46px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .dash-kpi-icon.navy {
            background: #f8fafc;
            border: 1.5px solid #cbd5e1;
            color: #0f172a;
        }

        .dash-kpi-icon.green {
            background: #f0fdf4;
            border: 1.5px solid #bbf7d0;
            color: #10b981;
        }

        .dash-kpi-icon.blue {
            background: #eff6ff;
            border: 1.5px solid #bfdbfe;
            color: #2563eb;
        }

        .dash-table-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .dash-quick-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .dash-btn-primary {
            background: #0f172a;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 8px 18px;
            font-size: 13.5px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: background 0.15s ease, transform 0.1s ease;
        }

        .dash-btn-primary:hover {
            background: #1e293b;
            transform: translateY(-1px);
        }

        .dash-btn-secondary {
            background: #ffffff;
            color: #0f172a;
            border: 1.5px solid #0f172a;
            border-radius: 8px;
            padding: 7px 16px;
            font-size: 13.5px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .dash-btn-secondary:hover {
            background: #f8fafc;
            transform: translateY(-1px);
        }

        .dash-bottom-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin-top: 20px;
            margin-bottom: 24px;
        }

        @media (max-width: 960px) {
            .dash-bottom-grid {
                grid-template-columns: 1fr;
            }
        }

        .dash-bottom-card {
            background: #ffffff;
            border: 1px solid var(--border-color, #e2e8f0);
            border-radius: 12px;
            padding: 18px 22px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
        }

        .dash-bottom-card-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 14px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 10px;
        }

        .dash-bottom-card-title {
            font-size: 15px;
            font-weight: 800;
            color: #0f172a;
            margin: 0;
        }

"""

if CSS_TARGET in content and ".dash-banner" not in content:
    content = content.replace(CSS_TARGET, DASHBOARD_CSS + CSS_TARGET)
    print("Injected Dashboard CSS.")
else:
    print("CSS target check: already present or not matched.")

# 3. HTML Replacement
OLD_HTML_REGEX = re.compile(
    r'<section id="view-dashboard" class="view-section active">.*?</section>',
    re.DOTALL
)

NEW_HTML = """<section id="view-dashboard" class="view-section active">
                <!-- Dashboard Header Banner -->
                <div class="dash-banner">
                    <div class="dash-banner-right">
                        <div class="dash-banner-icon">
                            <svg style="width: 22px; height: 22px;" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                                <polyline points="9 22 9 12 15 12 15 22"></polyline>
                            </svg>
                        </div>
                        <div>
                            <h1 class="dash-banner-title">الرئيسية</h1>
                            <p class="dash-banner-subtitle">نظرة عامة على عمليات الفحص والأبحاث والتقارير</p>
                        </div>
                    </div>
                    <!-- Faded Police Academy Background graphic on left side -->
                    <div class="dash-banner-bg" aria-hidden="true"></div>
                </div>

                <!-- Metrics & Statistics KPI Cards Grid (3 Cards in RTL) -->
                <div class="dash-kpis-container">
                    <!-- Card 1: Reference Corpus (قاعدة الأبحاث المرجعية) -->
                    <div class="dash-kpi-card" onclick="switchView('database')" title="انقر لفتح قاعدة الأبحاث الأساسية">
                        <div class="dash-kpi-info">
                            <div class="dash-kpi-header">
                                <span class="dash-kpi-title">قاعدة الأبحاث المرجعية</span>
                                <span class="dash-kpi-number" id="stat-total-papers">0</span>
                            </div>
                            <div class="dash-kpi-desc">
                                <svg class="nav-icon-svg" style="width:13px; height:13px; stroke:#0ea5e9;" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                <span>بحث مسجل ومفهرس للمقارنة</span>
                            </div>
                        </div>
                        <div class="dash-kpi-icon navy">
                            <svg style="width:24px; height:24px;" viewBox="0 0 24 24" fill="none" stroke="#0f172a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
                                <path d="M21 12v7c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                                <line x1="12" y1="5" x2="12" y2="22" stroke-dasharray="2 2" opacity="0.6"></line>
                            </svg>
                        </div>
                    </div>

                    <!-- Hidden placeholder for backwards compatibility with stat-preliminary-count -->
                    <span id="stat-preliminary-count" style="display:none;">0</span>

                    <!-- Card 2: Final Accepted Papers (الأبحاث المعتمدة نهائيًا) -->
                    <div class="dash-kpi-card accent-green" onclick="switchView('reports')" title="انقر لفتح الأبحاث المعتمدة نهائياً">
                        <div class="dash-kpi-info">
                            <div class="dash-kpi-header">
                                <span class="dash-kpi-title">الأبحاث المعتمدة نهائيًا</span>
                                <span class="dash-kpi-number green" id="stat-final-count">0</span>
                            </div>
                            <div class="dash-kpi-desc">
                                <svg class="nav-icon-svg" style="width:13px; height:13px; stroke:#10b981;" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                <span>أضيفت لقاعدة البيانات للمقارنة</span>
                            </div>
                        </div>
                        <div class="dash-kpi-icon green">
                            <svg style="width:24px; height:24px;" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                                <polyline points="9 12 11 14 15 10"></polyline>
                            </svg>
                        </div>
                    </div>

                    <!-- Card 3: Total Completed Scans (إجمالي عمليات الفحص) -->
                    <div class="dash-kpi-card accent-blue" onclick="switchView('reports')" title="انقر لفتح جميع تقارير الفحص">
                        <div class="dash-kpi-info">
                            <div class="dash-kpi-header">
                                <span class="dash-kpi-title">إجمالي عمليات الفحص</span>
                                <span class="dash-kpi-number blue" id="stat-total-scans">0</span>
                            </div>
                            <div class="dash-kpi-desc">
                                <svg class="nav-icon-svg" style="width:13px; height:13px; stroke:#2563eb;" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                                <span>أبحاث وتقارير تم فحصها وتحليلها</span>
                            </div>
                        </div>
                        <div class="dash-kpi-icon blue">
                            <svg style="width:24px; height:24px;" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                                <polyline points="10 9 9 9 8 9"></polyline>
                            </svg>
                        </div>
                    </div>
                </div>

                <!-- Recent Reports Card -->
                <div class="card" style="padding: 20px 24px; margin-bottom: 20px;">
                    <div class="dash-table-top">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <svg class="nav-icon-svg" style="width: 20px; height: 20px; stroke: #0f172a;" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                            <h3 class="section-title" style="margin-bottom: 0; font-size: 16px; font-weight: 800; color: #0f172a;">آخر تقارير الفحص والتقارير</h3>
                        </div>
                        <div class="dash-quick-actions">
                            <button type="button" class="dash-btn-primary" onclick="switchView('upload')" title="بدء فحص بحث جديد">
                                <svg style="width: 15px; height: 15px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                                <span>فحص بحث جديد</span>
                            </button>
                            <button type="button" class="dash-btn-secondary" onclick="switchView('reports')" title="عرض جميع التقارير">
                                <svg style="width: 15px; height: 15px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                                <span>عرض جميع التقارير</span>
                            </button>
                        </div>
                    </div>

                    <div class="dash-filter-toolbar" style="display: flex; justify-content: space-between; align-items: center; margin: 16px 0 14px 0; flex-wrap: wrap; gap: 12px;">
                        <div class="date-range-filter" data-date-filter="dashboard" style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span class="date-range-title" style="display: flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 700; color: #334155;">
                                <svg class="nav-icon-svg" style="width: 14px; height: 14px; stroke: #334155;" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                                الفترة الزمنية:
                            </span>
                            <label class="date-range-field" style="display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #475569;">
                                <span>من</span>
                                <input type="date" id="dashboard-date-from" aria-label="من تاريخ" style="border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; font-size: 12.5px; background: #ffffff;">
                            </label>
                            <label class="date-range-field" style="display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #475569;">
                                <span>إلى</span>
                                <input type="date" id="dashboard-date-to" aria-label="إلى تاريخ" style="border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; font-size: 12.5px; background: #ffffff;">
                            </label>
                            <button type="button" class="btn-filter-apply" onclick="applyDateFilter('dashboard')" style="background: #1e3a8a; color: #ffffff; border: none; border-radius: 6px; padding: 5px 14px; font-size: 12.5px; font-weight: 700; cursor: pointer;">تطبيق</button>
                            <button type="button" class="btn-filter-clear" onclick="clearDateFilter('dashboard')" style="background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer;">مسح</button>
                        </div>
                        <div>
                            <button type="button" class="btn-secondary" onclick="loadDashboardStats()" style="display: flex; align-items: center; gap: 6px; padding: 6px 14px; font-size: 12.5px; font-weight: 700; border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; color: #1e293b; cursor: pointer;">
                                <svg class="nav-icon-svg" style="width: 13px; height: 13px;" viewBox="0 0 24 24"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                                <span>تحديث</span>
                            </button>
                        </div>
                    </div>

                    <div style="overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <table class="custom-table" style="width: 100%; border-collapse: collapse; text-align: right;">
                            <thead>
                                <tr style="background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b;">عنوان البحث</th>
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b;">اسم الباحث</th>
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b;">تاريخ التحليل</th>
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b; text-align: center;">الحالة</th>
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b; text-align: center;">نسبة الاستلال</th>
                                    <th style="padding: 12px 16px; font-size: 13px; font-weight: 800; color: #1e293b; text-align: center;">الإجراءات</th>
                                </tr>
                            </thead>
                            <tbody id="dash-recent-table">
                                <!-- Populated dynamically by renderDashboardRecentTable() -->
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Bottom Two-Panel Grid (النشاط الأخير + حالة مكونات النظام) -->
                <div class="dash-bottom-grid">
                    <!-- Panel 1 (Right in RTL): Recent Activity (النشاط الأخير) -->
                    <div class="dash-bottom-card">
                        <div class="dash-bottom-card-header">
                            <svg style="width: 18px; height: 18px; stroke: #0f172a;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                            </svg>
                            <h3 class="dash-bottom-card-title">النشاط الأخير</h3>
                        </div>
                        <div id="dash-recent-activity-list" style="display: flex; flex-direction: column; gap: 10px;">
                            <!-- Populated dynamically by renderDashboardRecentActivity() -->
                        </div>
                    </div>

                    <!-- Panel 2 (Left in RTL): System Status (حالة مكونات النظام) -->
                    <div class="dash-bottom-card">
                        <div class="dash-bottom-card-header">
                            <svg style="width: 18px; height: 18px; stroke: #0f172a;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="3"></circle>
                                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                            </svg>
                            <h3 class="dash-bottom-card-title">حالة مكونات النظام</h3>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 14px;">
                            <!-- Component 1: محرك كشف الاستلال النصي -->
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 10px; color: #1e293b; font-size: 13.5px; font-weight: 700;">
                                    <svg style="width: 17px; height: 17px; stroke: #2563eb;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                                    <span>محرك كشف الاستلال النصي</span>
                                </div>
                                <span style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 999px; display: inline-flex; align-items: center; gap: 4px;">
                                    <svg style="width: 12px; height: 12px; stroke: #15803d;" viewBox="0 0 24 24" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                    جاهز
                                </span>
                            </div>

                            <!-- Component 2: التحليل الدلالي والمتقدم -->
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 10px; color: #1e293b; font-size: 13.5px; font-weight: 700;">
                                    <svg style="width: 17px; height: 17px; stroke: #4f46e5;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                                    <span>التحليل الدلالي والمتقدم</span>
                                </div>
                                <span style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 999px; display: inline-flex; align-items: center; gap: 4px;">
                                    <svg style="width: 12px; height: 12px; stroke: #15803d;" viewBox="0 0 24 24" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                    جاهز
                                </span>
                            </div>

                            <!-- Component 3: فحص الكتابة بالذكاء الاصطناعي (تجريبي) -->
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 10px; color: #1e293b; font-size: 13.5px; font-weight: 700;">
                                    <svg style="width: 17px; height: 17px; stroke: #0284c7;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>
                                    <span>فحص الكتابة بالذكاء الاصطناعي <span style="font-size: 11.5px; color: #0284c7; font-weight: 600;">(تجريبي)</span></span>
                                </div>
                                <span id="dash-status-ai" style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 999px; display: inline-flex; align-items: center; gap: 4px;">
                                    <svg style="width: 12px; height: 12px; stroke: #15803d;" viewBox="0 0 24 24" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                    جاهز
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>"""

content, count = OLD_HTML_REGEX.subn(NEW_HTML, content)
print(f"Replaced view-dashboard HTML: {count} match(es).")

# 4. JavaScript Enhancement
OLD_JS_REGEX = re.compile(
    r'async function loadDashboardStats\(\) \{.*?function renderDashboardRecentTable\(\) \{.*?\n        \}',
    re.DOTALL
)

NEW_JS = """        async function loadDashboardStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                if (document.getElementById('stat-total-papers')) {
                    document.getElementById('stat-total-papers').innerText = data.total_papers || 0;
                }
                if (document.getElementById('stat-preliminary-count')) {
                    document.getElementById('stat-preliminary-count').innerText = data.preliminary_count || 0;
                }
                if (document.getElementById('stat-final-count')) {
                    document.getElementById('stat-final-count').innerText = data.final_count || 0;
                }
                if (document.getElementById('stat-total-scans')) {
                    document.getElementById('stat-total-scans').innerText = data.total_scans || 0;
                }

                _cacheDashboardReports = data.recent_reports || [];
                renderDashboardRecentTable();
                renderDashboardRecentActivity(_cacheDashboardReports);
            } catch (e) {
                console.error('Failed to load dashboard stats', e);
            }
        }

        function renderDashboardRecentTable() {
            const tbody = document.getElementById('dash-recent-table');
            if (!tbody) return;

            const range = getDateRange('dashboard');
            const filteredReports = _cacheDashboardReports.filter(r => dateFallsWithinRange(r.date || r.created_at, range));
            let html = '';
            filteredReports.forEach(r => {
                let badgeStyle = 'background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd;';
                let statusLabel = r.status || 'مفحوص';
                if (statusLabel === 'قبول نهائي' || r.review_status === 'final_accepted') {
                    badgeStyle = 'background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0;';
                    statusLabel = 'قبول نهائي';
                } else if (statusLabel === 'قبول مبدئي' || r.review_status === 'preliminary_accepted') {
                    badgeStyle = 'background: #fef3c7; color: #b45309; border: 1px solid #fde68a;';
                    statusLabel = 'قبول مبدئي';
                } else if (statusLabel === 'مرفوض' || r.review_status === 'rejected') {
                    badgeStyle = 'background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca;';
                    statusLabel = 'مرفوض';
                }

                html += `
                    <tr style="border-bottom: 1px solid #f1f5f9; transition: background 0.1s ease;">
                        <td style="padding: 12px 16px; font-weight: 700; color: #1e293b;">
                            ${r.title}
                            ${r.reference_number ? `<div style="font-size:11px; font-weight:700; font-family:monospace; color:#0284c7; margin-top:3px;">${r.reference_number}</div>` : ''}
                        </td>
                        <td style="padding: 12px 16px; color: #334155; font-weight: 600;">${r.author || 'غير محدد'}</td>
                        <td style="padding: 12px 16px; font-size: 13px; color: #64748b; font-family: monospace; white-space: nowrap;">${r.date || ''}</td>
                        <td style="padding: 12px 16px; text-align: center;">
                            <span style="font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; display: inline-block; ${badgeStyle}">${statusLabel}</span>
                        </td>
                        <td style="padding: 12px 16px; text-align: center; font-weight: 800; font-size: 13.5px; color: #0f172a;">${r.pct}%</td>
                        <td style="padding: 12px 16px; text-align: center;">
                            <button type="button" class="btn-secondary" style="padding: 4px 10px; border-radius: 6px; border: 1px solid #cbd5e1; background: #ffffff; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;" onclick="openReport('${r.id}')" title="عرض التقرير">
                                <svg style="width: 15px; height: 15px; stroke: #0f172a;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                            </button>
                        </td>
                    </tr>
                `;
            });
            tbody.innerHTML = html || getEmptyStateHtml('لا توجد عمليات فحص سابقة', 'ستظهر هنا أحدث الأبحاث المفحوصة فور إجراء أول عملية تحليل.', 6);
        }

        function renderDashboardRecentActivity(reports) {
            const listEl = document.getElementById('dash-recent-activity-list');
            if (!listEl) return;
            if (!reports || reports.length === 0) {
                listEl.innerHTML = '<div style="text-align: center; color: #94a3b8; font-size: 13px; padding: 20px 0;">لا توجد أنشطة حديثة متاحة للعرض</div>';
                return;
            }
            const topReports = reports.slice(0, 5);
            let html = '';
            topReports.forEach((r, idx) => {
                let iconSvg = '';
                let actionText = '';
                if (r.review_status === 'final_accepted') {
                    if (idx === 1) {
                        iconSvg = `<svg style="width:16px; height:16px; stroke:#10b981; flex-shrink:0;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>`;
                        actionText = 'تم اعتماد بحث وإضافته لقاعدة المراجع';
                    } else {
                        iconSvg = `<svg style="width:16px; height:16px; stroke:#10b981; flex-shrink:0;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>`;
                        actionText = `تم قبول بحث نهائياً: ${r.title}`;
                    }
                } else {
                    iconSvg = `<svg style="width:16px; height:16px; stroke:#2563eb; flex-shrink:0;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`;
                    actionText = `تم فحص بحث جديد: ${r.title}`;
                }

                html += `
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 13px; padding: 6px 0; border-bottom: 1px solid #f8fafc;">
                        <div style="display: flex; align-items: center; gap: 8px; color: #1e293b; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 75%;">
                            ${iconSvg}
                            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${actionText}">${actionText}</span>
                        </div>
                        <div style="font-size: 11.5px; color: #64748b; font-family: monospace; white-space: nowrap; direction: ltr;">
                            ${r.date || ''}
                        </div>
                    </div>
                `;
            });
            listEl.innerHTML = html;
        }"""

content, js_count = OLD_JS_REGEX.subn(NEW_JS, content)
print(f"Replaced JS loadDashboardStats / renderDashboardRecentTable: {js_count} match(es).")

with open(INDEX_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("Saved enhanced templates/index.html successfully!")
