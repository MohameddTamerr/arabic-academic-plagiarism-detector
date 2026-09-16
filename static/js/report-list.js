// Dedicated report archive. Existing report detail rendering remains unchanged.
async function loadReportList(page = 1) {
    const body = document.getElementById('report-list-body');
    const pager = document.getElementById('report-list-pagination');
    if (!body) return;
    const params = new URLSearchParams({page, page_size: 20});
    for (const key of ['q', 'date_from', 'date_to', 'review_status', 'scan_status']) {
        const value = document.getElementById('report-filter-' + key).value;
        if (value) params.set(key, value);
    }
    try {
        const response = await fetch('/api/reports?' + params);
        const data = await response.json();
        if (!response.ok) throw new Error(extractApiError(data, `HTTP ${response.status}`));
        body.replaceChildren();
        for (const report of data.reports) {
            const row = body.insertRow();
            for (const value of [report.reference_number || report.id, report.title, report.author,
                report.created_at, report.scan_status_label, report.overall_pct + '%', report.review_status_label]) {
                row.insertCell().textContent = value ?? '—';
            }
            const button = document.createElement('button');
            button.className = 'btn-secondary';
            button.textContent = 'عرض التقرير';
            button.onclick = () => openReport(report.id);
            row.insertCell().append(button);
        }
        if (!data.reports.length) body.innerHTML = '<tr><td colspan="8">لا توجد تقارير مطابقة</td></tr>';
        pager.replaceChildren();
        pager.append(document.createTextNode(`صفحة ${data.page} من ${data.total_pages} — ${data.total_items} تقرير `));
        for (const [label, target, enabled] of [['السابق', page - 1, data.has_prev], ['التالي', page + 1, data.has_next]]) {
            const button = document.createElement('button');
            button.className = 'btn-secondary'; button.textContent = label; button.disabled = !enabled;
            button.onclick = () => loadReportList(target); pager.append(button);
        }
    } catch (error) {
        body.replaceChildren();
        const cell = body.insertRow().insertCell(); cell.colSpan = 8;
        cell.textContent = 'تعذر تحميل التقارير: ' + error.message;
        console.error('Report archive failed', error);
    }
}

function closeReportDetail() {
    const panel = document.getElementById('report-detail-panel');
    if (panel) panel.hidden = true;
}
