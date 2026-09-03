# -*- coding: utf-8 -*-
"""
وحدة تصدير تقرير الفحص الأكاديمي (Print-Ready HTML Exporter):
- تقرير تحليلي رسمي ملون بتصميم أنيق يدعم اللغة العربية واتجاه RTL.
- مخصص للطباعة الورقية (Print Styling) وحفظه كـ PDF.
- يعرض النسبتين: الإجمالية وغير الموثقة، وأرقام الصفحات المصدرية، ومؤشرات الذكاء الاصطناعي مع التنبيه.
"""

import html


def export_report_to_html(report: dict) -> str:
    """توليد ملف HTML كامل ومستقل للتقرير الأكاديمي."""
    rep_id = html.escape(str(report.get('id', '')))
    title = html.escape(str(report.get('title', 'بحث بدون عنوان')))
    author = html.escape(str(report.get('author', 'غير محدد')))
    date = html.escape(str(report.get('date', '')))
    status = html.escape(str(report.get('status', 'مفحوص')))

    overall_pct = report.get('overall_pct', 0.0)
    problematic_pct = report.get('problematic_pct', report.get('copied_pct', 0.0) + report.get('paraphrase_pct', 0.0))
    copied_pct = report.get('copied_pct', 0.0)
    para_pct = report.get('paraphrase_pct', 0.0)
    cited_pct = report.get('cited_pct', 0.0)

    ai_data = report.get('ai_analysis', {})
    ai_level = html.escape(str(ai_data.get('indicator_level', 'منخفض')))
    ai_score = ai_data.get('score', 0)
    ai_warning = html.escape(str(ai_data.get('warning', '')))

    sources = report.get('sources', [])
    segments = report.get('segments', [])
    page_alert = report.get('page_limit_alert', {})

    # توليد صفوف جدول المصادر
    sources_html = []
    for s in sources:
        s_title = html.escape(str(s.get('title', '')))
        s_author = html.escape(str(s.get('author', 'غير محدد')))
        s_pct = s.get('pct', 0.0)
        s_words = s.get('matched_words', s.get('words', 0))
        s_pages = s.get('estimated_pages', s.get('pages', 0.0))
        s_pages_display = html.escape(str(s.get('matched_pages_display', 'غير متاح')))

        sources_html.append(f"""
        <tr>
            <td style="font-weight: 600;">{s_title}</td>
            <td>{s_author}</td>
            <td style="text-align: center; color: #b91c1c; font-weight: bold;">{s_pct}%</td>
            <td style="text-align: center;">{s_words}</td>
            <td style="text-align: center;">{s_pages} <small style="color:#64748b;">(تقديري)</small></td>
            <td style="text-align: center; font-family: monospace;">{s_pages_display}</td>
        </tr>
        """)

    sources_table_body = "".join(sources_html) if sources_html else "<tr><td colspan='6' style='text-align:center;'>لم يتم تسجيل مصادر متطابقة.</td></tr>"

    # توليد شواهد الفقرات
    evidence_html = []
    for seg in segments:
        text_content = html.escape(str(seg.get('text', '')))
        seg_status = seg.get('status', 'original')
        match_type = seg.get('match_type', 'ORIGINAL')
        source_title = html.escape(str(seg.get('source_title', '')))
        source_page_disp = html.escape(str(seg.get('source_page_display', 'غير متاح')))
        pct = seg.get('pct', 0)

        if seg_status == 'copied':
            bg = '#fee2e2'
            border = '#ef4444'
            badge = f"<span class='badge badge-copy'>نسخ حرفي مباشر ({pct}%)</span>"
        elif seg_status == 'paraphrased':
            bg = '#ffedd5'
            border = '#f97316'
            badge = f"<span class='badge badge-para'>إعادة صياغة محتملة ({pct}%)</span>"
        elif seg_status == 'cited':
            bg = '#ecfdf5'
            border = '#10b981'
            badge = "<span class='badge badge-cite'>اقتباس موثق بنظام التوثيق</span>"
        elif seg.get('is_bibliography'):
            bg = '#f1f5f9'
            border = '#94a3b8'
            badge = "<span class='badge badge-bib'>قائمة المراجع (مستبعدة)</span>"
        else:
            continue  # لا نعرض المقاطع الأصلية في الشواهد لتخفيف التقرير

        meta_info = f"<div class='seg-meta'>المرجع: «{source_title}» | صفحة المرجع: {source_page_disp}</div>" if source_title else ""
        matched_passage = html.escape(str(seg.get('matched_text', '')))
        src_box = f"""
        <div style="margin-top: 8px; padding: 8px 12px; background: rgba(255,255,255,0.85); border-radius: 6px; font-size: 13px; color: #334155; border: 1px dashed #cbd5e1;">
            <strong style="color: #0f2b5c;">النص المطابق في المرجع المصدر:</strong>
            <div style="margin-top: 4px; font-style: italic; color: #475569;">«{matched_passage}»</div>
        </div>
        """ if matched_passage else ""

        evidence_html.append(f"""
        <div class="evidence-card" style="background-color: {bg}; border-right: 4px solid {border};">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                {badge}
                {meta_info}
            </div>
            <div style="margin-bottom: 4px;"><strong>النص المفحوص:</strong></div>
            <p class="seg-text" style="margin-top: 2px;">{text_content}</p>
            {src_box}
        </div>
        """)

    evidence_body = "".join(evidence_html) if evidence_html else "<p style='color: #64748b;'>لم يتم العثور على شواهد استلال.</p>"

    # تنبيه تجاوز الصفحات المسموحة
    alert_box = ""
    if page_alert.get('has_limit_exceeded'):
        details_list = "".join(f"<li>{html.escape(d)}</li>" for d in page_alert.get('details', []))
        alert_box = f"""
        <div class="alert-box">
            <strong>⚠️ تنبيه أكاديمي - تجاوز الحد المسموح للاقتباس من مرجع واحد (5 صفحات):</strong>
            <ul>{details_list}</ul>
        </div>
        """

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <title>تقرير كشف الاستلال العلمي والأمانة الأكاديمية - {title}</title>
    <style>
        body {{
            font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 30px;
            direction: rtl;
        }}
        .report-header {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        }}
        .grid-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .stat-val {{
            font-size: 26px;
            font-weight: 800;
            margin-top: 6px;
        }}
        .stat-label {{
            font-size: 13px;
            color: #64748b;
        }}
        .table-wrap {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 24px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px 16px;
            text-align: right;
            border-bottom: 1px solid #f1f5f9;
        }}
        th {{
            background-color: #f8fafc;
            color: #475569;
            font-weight: 700;
            font-size: 13px;
        }}
        .badge {{
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
        }}
        .badge-copy {{ background: #fee2e2; color: #b91c1c; }}
        .badge-para {{ background: #ffedd5; color: #c2410c; }}
        .badge-cite {{ background: #ecfdf5; color: #047857; }}
        .badge-bib {{ background: #f1f5f9; color: #475569; }}
        .evidence-card {{
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 14px;
        }}
        .seg-text {{
            font-size: 15px;
            line-height: 1.7;
            margin: 0;
        }}
        .seg-meta {{
            font-size: 12px;
            color: #64748b;
            font-weight: 600;
        }}
        .alert-box {{
            background: #fef2f2;
            border: 1px solid #fca5a5;
            color: #991b1b;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            font-size: 14px;
        }}
        .ai-card {{
            background: #faf5ff;
            border: 1px solid #e9d5ff;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        @media print {{
            body {{ background: #ffffff; padding: 0; }}
            .no-print {{ display: none; }}
            .report-header, .table-wrap, .ai-card {{ box-shadow: none; border: 1px solid #cbd5e1; }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f2b5c; padding-bottom: 16px;">
            <div>
                <h1 style="color: #0f2b5c; margin: 0 0 6px 0; font-size: 22px;">تقرير كشف الاستلال العلمي والأمانة الأكاديمية</h1>
                <p style="margin: 0; color: #64748b; font-size: 13px;">نظام المراجعة الأكاديمية الذاتي (100% Offline Integrity System)</p>
            </div>
            <div style="text-align: left;">
                <div style="font-weight: 700; color: #0f2b5c;">رقم التقرير: #{rep_id}</div>
                <div style="font-size: 12px; color: #64748b;">تاريخ الفحص: {date}</div>
            </div>
        </div>

        <div style="display: flex; gap: 30px; margin-top: 16px; font-size: 14px;">
            <div><strong>عنوان البحث:</strong> {title}</div>
            <div><strong>اسم الباحث:</strong> {author}</div>
            <div><strong>الحالة:</strong> {status}</div>
        </div>

        <div class="grid-stats">
            <div class="stat-card">
                <div class="stat-label">نسبة الاستلال الإجمالية</div>
                <div class="stat-val" style="color: #0f2b5c;">{overall_pct}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">الاستلال غير الموثق (المقلق)</div>
                <div class="stat-val" style="color: #b91c1c;">{problematic_pct}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">النسخ الحرفي المباشر</div>
                <div class="stat-val" style="color: #ef4444;">{copied_pct}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">إعادة الصياغة</div>
                <div class="stat-val" style="color: #f97316;">{para_pct}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">اقتباس موثق بنظام التوثيق</div>
                <div class="stat-val" style="color: #10b981;">{cited_pct}%</div>
            </div>
        </div>
    </div>

    {alert_box}

    <!-- مؤشرات الذكاء الاصطناعي -->
    <div class="ai-card">
        <h3 style="color: #6b21a8; margin-top: 0;">🤖 مؤشرات الأسلوب اللغوي الشبيه بالذكاء الاصطناعي</h3>
        <p><strong>مستوى المؤشرات:</strong> {ai_level} (الدرجة الاستئناسية: {ai_score} من 100)</p>
        <p style="font-size: 12px; color: #6b21a8; background: #f3e8ff; padding: 10px; border-radius: 6px; margin-bottom: 0;">
            ⚠️ {ai_warning}
        </p>
    </div>

    <!-- جدول المراجع المصدرية -->
    <div class="table-wrap">
        <div style="padding: 16px 20px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: #0f2b5c;">
            جدول المراجع المصدرية وعزو الصفحات
        </div>
        <table>
            <thead>
                <tr>
                    <th>عنوان المرجع المصدر</th>
                    <th>المؤلف</th>
                    <th style="text-align: center;">نسبة التطابق</th>
                    <th style="text-align: center;">الكلمات المتطابقة</th>
                    <th style="text-align: center;">الصفحات التقديرية</th>
                    <th style="text-align: center;">أرقام صفحات المرجع الأصلية</th>
                </tr>
            </thead>
            <tbody>
                {sources_table_body}
            </tbody>
        </table>
    </div>

    <!-- شواهد الاستلال -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px;">
        <h3 style="color: #0f2b5c; margin-top: 0; margin-bottom: 16px;">شواهد النصوص والفقرات المستخرجة</h3>
        {evidence_body}
    </div>
</body>
</html>
"""
