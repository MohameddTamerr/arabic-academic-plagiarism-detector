/* Offline viewer: bundled application controls and local PyMuPDF page images. */
let pdfView = {base: '', page: 1, count: 0, scale: 1, request: 0};
async function openInternalPdf(kind, id, page = 1, fileIndex = null) {
    const request = ++pdfView.request;
    const query = fileIndex == null ? '' : '?file_index=' + encodeURIComponent(fileIndex);
    const base = '/api/pdf/' + kind + '/' + encodeURIComponent(id);
    try {
        const response = await fetch(base + '/info' + query);
        const info = await response.json();
        if (!response.ok) throw new Error(getErrorMessage(info, 'ملف PDF غير متاح'));
        if (request !== pdfView.request) return;
        pdfView = {base, query, page: Math.max(1, Math.min(Number(page) || 1, info.page_count)), count: info.page_count, scale: 1, request};
        document.getElementById('internal-pdf-modal').style.display = 'flex';
        showPdfPage();
    } catch (error) { showToast(error.message || 'تعذر عرض PDF', 'error'); }
}
function showPdfPage() {
    const image = document.getElementById('internal-pdf-image');
    image.src = pdfView.base + '/page' + (pdfView.query || '?') + (pdfView.query ? '&' : '') + 'page=' + pdfView.page;
    image.style.width = (pdfView.scale * 100) + '%';
    document.getElementById('internal-pdf-number').value = pdfView.page;
    document.getElementById('internal-pdf-total').textContent = '/ ' + pdfView.count;
    document.getElementById('internal-pdf-prev').disabled = pdfView.page <= 1;
    document.getElementById('internal-pdf-next').disabled = pdfView.page >= pdfView.count;
    image.onerror = () => showToast('تعذر عرض الصفحة؛ تحقق من صلاحية المستند والجلسة', 'error');
}
function changePdfPage(delta) { pdfView.page = Math.max(1, Math.min(pdfView.count, pdfView.page + delta)); showPdfPage(); }
function jumpPdfPage(value) { pdfView.page = Math.max(1, Math.min(pdfView.count, Number(value) || 1)); showPdfPage(); }
function zoomPdf(delta) { pdfView.scale = Math.max(.25, Math.min(3, pdfView.scale + delta)); showPdfPage(); }
function fitPdfWidth() { pdfView.scale = 1; showPdfPage(); }

function literalEvidence(text, source) {
    const tokens = value => Array.from(String(value || '').matchAll(/[\p{L}\p{N}]+/gu));
    const submitted = tokens(text), matched = tokens(source);
    const pairs = new Set(matched.slice(0,-1).map((t,i) => t[0] + '\0' + matched[i+1][0]));
    const indices = new Set();
    submitted.slice(0,-1).forEach((t,i) => { if (pairs.has(t[0] + '\0' + submitted[i+1][0])) { indices.add(i); indices.add(i+1); } });
    let result = '', cursor = 0;
    submitted.forEach((token,i) => {
        result += escapeHtml(text.slice(cursor,token.index));
        result += indices.has(i) ? '<mark>' + escapeHtml(token[0]) + '</mark>' : escapeHtml(token[0]);
        cursor = token.index + token[0].length;
    });
    return result + escapeHtml(String(text || '').slice(cursor));
}
function attachPdfEvidence(report) {
    const target = document.getElementById('pdf-evidence-links');
    if (!target) return;
    target.replaceChildren();
    function button(label, kind, id, page, index) {
        const element = document.createElement('button'); element.className = 'btn-secondary'; element.textContent = label;
        element.style.margin = '4px';
        element.onclick = () => openInternalPdf(kind, id, page, index); return element;
    }
    const container = document.createElement('div');
    container.style.cssText = 'display:flex; flex-wrap:wrap; gap:8px; align-items:center;';
    
    if (report.is_combined_thesis) {
        (report.part_summaries || []).forEach(part => {
            container.append(button('عارض الجزء: ' + (part.part_title || part.part_id), 'part', part.part_id, 1));
        });
    } else if (report.file_count > 1) {
        (report.file_names || []).forEach((name,index) => container.append(button('عرض ملف: ' + name, 'report', report.id, 1, index)));
    } else {
        container.append(button('فتح البحث مع التحديد في عارض PDF', 'report', report.id, 1));
    }
    target.append(container);
}
