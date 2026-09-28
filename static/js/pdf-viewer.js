/* Offline viewer: bundled application controls and local PyMuPDF page images. */
let pdfView = {base: '', page: 1, count: 0, scale: 1, request: 0, highlights: [], currentHighlight: null, evidenceIndex: [], evidencePosition: -1, evidenceIndexLoaded: false, highlightFilters: {all: true, copied: true, paraphrased: true, cited: true}};
let pdfHighlights = {};  // Cache highlights per page

async function openInternalPdf(kind, id, page = 1, fileIndex = null, targetEvidenceId = null) {
    const request = ++pdfView.request;
    const query = fileIndex == null ? '' : '?file_index=' + encodeURIComponent(fileIndex);
    const base = '/api/pdf/' + kind + '/' + encodeURIComponent(id);
    try {
        const response = await fetch(base + '/info' + query);
        const info = await response.json();
        if (!response.ok) throw new Error(getErrorMessage(info, 'ملف PDF غير متاح'));
        if (request !== pdfView.request) return;
        pdfView = {base, query, page: Math.max(1, Math.min(Number(page) || 1, info.page_count)), count: info.page_count, scale: 1, request, highlights: [], currentHighlight: null, evidenceIndex: [], evidencePosition: -1, evidenceIndexLoaded: false, highlightFilters: {all: true, copied: true, paraphrased: true, cited: true}, targetEvidenceId};
        pdfHighlights = {};
        document.getElementById('internal-pdf-modal').style.display = 'flex';
        showPdfPage();
    } catch (error) { showToast(error.message || 'تعذر عرض PDF', 'error'); }
}

async function loadPdfHighlights() {
    if (!pdfView.base || pdfView.query === undefined) return [];

    const cacheKey = pdfView.page;
    if (pdfHighlights[cacheKey]) return pdfHighlights[cacheKey];

    try {
        const url = pdfView.base + '/highlights' + (pdfView.query || '?') + (pdfView.query ? '&' : '') + 'page=' + pdfView.page;
        const response = await fetch(url);
        if (!response.ok) return [];
        const data = await response.json();
        pdfHighlights[cacheKey] = data.highlights || [];
        return pdfHighlights[cacheKey];
    } catch (error) {
        console.error('Failed to load highlights:', error);
        return [];
    }
}

async function showPdfPage() {
    const image = document.getElementById('internal-pdf-image');
    image.style.width = (pdfView.scale * 100) + '%';
    document.getElementById('internal-pdf-number').value = pdfView.page;
    document.getElementById('internal-pdf-total').textContent = '/ ' + pdfView.count;
    document.getElementById('internal-pdf-prev').disabled = pdfView.page <= 1;
    document.getElementById('internal-pdf-next').disabled = pdfView.page >= pdfView.count;
    image.onerror = () => showToast('تعذر عرض الصفحة؛ تحقق من صلاحية المستند والجلسة', 'error');

    // Load and render highlights after image loads
    image.onload = async () => {
        const highlights = await loadPdfHighlights();
        renderPdfHighlights(highlights);
        // Focus target highlight if specified
        if (pdfView.targetEvidenceId) {
            const focused = focusHighlightByEvidenceId(pdfView.targetEvidenceId, 'pdf-highlights-overlay');
            if (focused) pdfView.targetEvidenceId = null;
        }
    };
    image.src = pdfView.base + '/page' + (pdfView.query || '?') + (pdfView.query ? '&' : '') + 'page=' + pdfView.page;
}

function getHighlightStatus(highlight) {
    const status = String(highlight.status || '').toLowerCase();
    const matchType = (highlight.match_type || '').toUpperCase();
    if (status === 'copied' || matchType === 'EXACT' || matchType === 'DIRECT' || matchType === 'DIRECT COPY') return 'copied';
    if (status === 'paraphrased' || matchType === 'PARAPHRASE') return 'paraphrased';
    if (status === 'cited' || matchType === 'CITED' || matchType === 'CITED QUOTE') return 'cited';
    return null;
}

function shouldShowHighlight(highlight) {
    const status = getHighlightStatus(highlight);
    return Boolean(status) && (pdfView.highlightFilters.all || pdfView.highlightFilters[status]);
}

function renderPdfHighlights(highlights) {
    const image = document.getElementById('internal-pdf-image');
    const container = image.parentElement;
    let overlay = document.getElementById('pdf-highlights-overlay');

    if (!overlay) {
        overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        overlay.id = 'pdf-highlights-overlay';
        overlay.style.cssText = 'position:absolute; top:0; left:0; cursor:pointer; pointer-events:auto;';
        if (container.style.position !== 'relative' && container.style.position !== 'absolute') {
            container.style.position = 'relative';
        }
        container.appendChild(overlay);
    }

    overlay.setAttribute('width', image.offsetWidth || image.width);
    overlay.setAttribute('height', image.offsetHeight || image.height);
    overlay.innerHTML = '';

    const imgWidth = image.offsetWidth || image.width;
    const imgHeight = image.offsetHeight || image.height;
    highlights.forEach((h, idx) => {
        if (!h.rect || h.rect.length < 4 || !shouldShowHighlight(h)) return;

        const [x0, y0, x1, y1] = h.rect;
        const coordinateWidth = Number(h.page_width) || ((image.naturalWidth || 1) / 1.25);
        const coordinateHeight = Number(h.page_height) || ((image.naturalHeight || 1) / 1.25);
        const scaleX = imgWidth / coordinateWidth;
        const scaleY = imgHeight / coordinateHeight;
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x0 * scaleX);
        rect.setAttribute('y', y0 * scaleY);
        rect.setAttribute('width', Math.max(1, (x1 - x0) * scaleX));
        rect.setAttribute('height', Math.max(1, (y1 - y0) * scaleY));
        rect.setAttribute('fill', h.color);
        rect.setAttribute('fill-opacity', '0.35');
        rect.setAttribute('stroke', 'none');
        rect.style.cursor = 'pointer';
        rect.style.transition = 'fill-opacity 0.15s';
        rect.title = `${h.status}: ${h.source_title}`;
        rect.dataset.highlightIndex = idx;
        rect.dataset.highlightData = JSON.stringify(h);

        rect.addEventListener('mouseover', () => {
            rect.setAttribute('fill-opacity', '0.55');
        });
        rect.addEventListener('mouseout', () => {
            if (rect.dataset.focused !== 'true') {
                rect.setAttribute('fill-opacity', '0.35');
            }
        });
        rect.addEventListener('click', (e) => {
            e.stopPropagation();
            focusHighlight(rect);
            showHighlightEvidence(h);
        });

        overlay.appendChild(rect);
    });

    pdfView.highlights = highlights;
}

function focusHighlight(rectElement) {
    // Remove focus from previous highlight
    const prevFocused = document.querySelector('[data-focused="true"]');
    if (prevFocused) {
        prevFocused.setAttribute('data-focused', 'false');
        prevFocused.setAttribute('fill-opacity', '0.35');
    }

    // Focus new highlight with pulse effect
    rectElement.setAttribute('data-focused', 'true');
    rectElement.setAttribute('fill-opacity', '0.65');
    rectElement.style.animation = 'pdf-highlight-pulse 0.5s ease-out';
}

function focusHighlightByEvidenceId(evidenceId, overlayId = 'pdf-highlights-overlay') {
    // Match highlight by text content
    const overlay = document.getElementById(overlayId);
    if (!overlay) return false;

    const rects = overlay.querySelectorAll('rect');
    for (const rect of rects) {
        try {
            const data = JSON.parse(rect.dataset.highlightData || '{}');
            const needle = String(evidenceId || '').trim().substring(0, 20);
            if (needle && data.text && data.text.includes(needle)) {
                focusHighlight(rect);
                rect.scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'});
                return true;
            }
        } catch (e) {}
    }
    return false;
}

function buildSourceEvidenceUrl(sourceId, sourcePage, matchedText, sourceTitle, sourceReportId = null) {
    const targetId = sourceReportId || sourceId;
    if (targetId === null || targetId === undefined || targetId === '') return '';
    const params = new URLSearchParams();
    params.set('page', Math.max(1, Number(sourcePage) || 1));
    params.set('text', String(matchedText || '').slice(0, 4000));
    params.set('title', String(sourceTitle || 'الرسالة أو الجزء المصدر'));
    const route = sourceReportId ? '/source-report-viewer/' : '/source-viewer/';
    return `${route}${encodeURIComponent(targetId)}?${params.toString()}`;
}

function openSourceEvidence(sourceId, sourcePage, matchedText, sourceTitle) {
    const url = buildSourceEvidenceUrl(sourceId, sourcePage, matchedText, sourceTitle);
    if (!url) {
        showToast('بيانات الرسالة أو الجزء المصدر غير متاحة لهذا الشاهد', 'warning');
        return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
}

function showHighlightEvidence(highlight) {
    const status = getHighlightStatus(highlight);
    let badge = 'اقتباس موثق';
    if (status === 'copied') badge = 'نسخ مباشر';
    else if (status === 'paraphrased') badge = 'إعادة صياغة';

    let popup = document.getElementById('pdf-highlight-popup');
    if (!popup) {
        popup = document.createElement('div');
        popup.id = 'pdf-highlight-popup';
        popup.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: white;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 16px;
            max-width: 400px;
            max-height: 300px;
            overflow-y: auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 12100;
            font-family: Cairo, system-ui, sans-serif;
            direction: rtl;
        `;
        document.body.appendChild(popup);
    }

    const sourceUrl = buildSourceEvidenceUrl(
        highlight.source_id,
        highlight.source_page,
        highlight.matched_text,
        highlight.source_title,
        highlight.source_report_id
    );
    const sourceTitle = escapeHtml(highlight.source_title || 'مرجع غير متاح');
    popup.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px; gap: 8px;">
            <div>
                <div style="background: ${highlight.color}; color: white; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 8px;">
                    ${badge}
                </div>
                ${sourceUrl
                    ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" style="font-weight:700; color:#0f2b5c; font-size:13px; text-decoration:underline;">${sourceTitle}</a>`
                    : `<div style="font-weight:700; color:#0f2b5c; font-size:13px;">${sourceTitle}</div>`}
                <div style="font-size: 12px; color: #64748b;">${escapeHtml(highlight.source_author || 'غير متاح')}</div>
            </div>
            <button style="background: none; border: none; cursor: pointer; font-size: 16px; color: #64748b;" onclick="this.closest('#pdf-highlight-popup').style.display = 'none';">✕</button>
        </div>
        <div style="border-top: 1px solid #e2e8f0; padding-top: 12px; margin-top: 12px;">
            <div style="font-size: 11px; font-weight: 700; color: #475569; margin-bottom: 4px;">التطابق: ${highlight.pct ? highlight.pct + '%' : 'غير متاح'}</div>
            <div style="font-size: 11px; font-weight: 700; color: #475569; margin-bottom: 8px;">صفحة المرجع: ${highlight.source_page || 'غير محدد'}</div>
            <div style="font-size: 12px; background: #f8fafc; padding: 8px; border-radius: 4px; margin-bottom: 8px; color: #0f172a;" dir="auto">
                ${escapeHtml(highlight.matched_text || '')}
            </div>
            ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" style="display:block; text-align:center; background:#102f63; color:white; text-decoration:none; padding:7px 10px; border-radius:6px; font-size:12px; font-weight:700;">فتح الرسالة/الجزء المصدر في نافذة جديدة ↗</a>` : ''}
        </div>
    `;
    popup.style.display = 'block';
}

function changePdfPage(delta) {
    pdfView.page = Math.max(1, Math.min(pdfView.count, pdfView.page + delta));
    showPdfPage();
    showInlinePdfPage();
}
function jumpPdfPage(value) { pdfView.page = Math.max(1, Math.min(pdfView.count, Number(value) || 1)); showPdfPage(); showInlinePdfPage(); }

async function loadPdfEvidenceIndex() {
    if (pdfView.evidenceIndexLoaded) return pdfView.evidenceIndex || [];
    if (!pdfView.base) return [];
    try {
        const url = pdfView.base + '/evidence-index' + (pdfView.query || '');
        const response = await fetch(url);
        const data = await response.json();
        if (!response.ok) throw new Error(getErrorMessage(data, 'تعذر تحميل مواضع التطابق'));
        pdfView.evidenceIndex = Array.isArray(data.items) ? data.items : [];
        pdfView.evidenceIndexLoaded = true;
        updateEvidenceNavigation();
        return pdfView.evidenceIndex;
    } catch (error) {
        console.error('Failed to load evidence index:', error);
        showToast(error.message || 'تعذر تحميل مواضع التطابق', 'warning');
        return [];
    }
}

function updateEvidenceNavigation() {
    const total = (pdfView.evidenceIndex || []).length;
    const current = total && pdfView.evidencePosition >= 0 ? pdfView.evidencePosition + 1 : 0;
    ['inline-evidence-position', 'modal-evidence-position'].forEach(id => {
        const label = document.getElementById(id);
        if (label) label.textContent = `${current} / ${total}`;
    });
    ['inline-evidence-prev', 'modal-evidence-prev'].forEach(id => {
        const button = document.getElementById(id);
        if (button) button.disabled = !total || pdfView.evidencePosition <= 0;
    });
    ['inline-evidence-next', 'modal-evidence-next'].forEach(id => {
        const button = document.getElementById(id);
        if (button) button.disabled = !total || (pdfView.evidencePosition >= total - 1 && pdfView.evidencePosition >= 0);
    });
}

async function jumpToEvidence(direction = 1, first = false) {
    const items = await loadPdfEvidenceIndex();
    if (!items.length) {
        showToast('لا توجد مواضع تطابق قابلة للتحديد داخل المستند', 'info');
        return;
    }
    let targetPosition;
    if (first || pdfView.evidencePosition < 0) targetPosition = 0;
    else targetPosition = Math.max(0, Math.min(items.length - 1, pdfView.evidencePosition + direction));

    pdfView.evidencePosition = targetPosition;
    const target = items[targetPosition];
    pdfView.page = target.page;
    pdfView.targetEvidenceId = target.text;
    updateEvidenceNavigation();
    showInlinePdfPage();

    const modal = document.getElementById('internal-pdf-modal');
    if (modal && getComputedStyle(modal).display !== 'none') showPdfPage();
}

function jumpToFirstEvidence() { jumpToEvidence(1, true); }
function zoomPdf(delta) { pdfView.scale = Math.max(.25, Math.min(3, pdfView.scale + delta)); showPdfPage(); showInlinePdfPage(); }
function fitPdfWidth() {
    const modal = document.getElementById('internal-pdf-modal');
    const modalOpen = modal && getComputedStyle(modal).display !== 'none';
    const image = document.getElementById(modalOpen ? 'internal-pdf-image' : 'inline-pdf-image');
    const viewport = document.getElementById(modalOpen ? 'pdf-container' : 'inline-pdf-container');
    const naturalWidth = image?.naturalWidth || 0;
    const availableWidth = Math.max(1, (viewport?.clientWidth || naturalWidth) - 40);
    pdfView.scale = naturalWidth ? Math.max(.25, Math.min(3, availableWidth / naturalWidth)) : 1;
    showPdfPage();
    showInlinePdfPage();
}

function toggleHighlightFilter(status) {
    if (status === 'all') {
        const allOn = pdfView.highlightFilters.all;
        pdfView.highlightFilters = {all: !allOn, copied: !allOn, paraphrased: !allOn, cited: !allOn};
    } else {
        pdfView.highlightFilters[status] = !pdfView.highlightFilters[status];
        pdfView.highlightFilters.all = pdfView.highlightFilters.copied && pdfView.highlightFilters.paraphrased && pdfView.highlightFilters.cited;
    }
    const highlights = pdfHighlights[pdfView.page] || [];
    renderPdfHighlights(highlights);
    renderInlinePdfHighlights(highlights);
    updateFilterButtons();
}

function updateFilterButtons() {
    ['all', 'copied', 'paraphrased', 'cited'].forEach(status => {
        [`pdf-filter-${status}`, `inline-pdf-filter-${status}`].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.style.opacity = pdfView.highlightFilters[status] ? '1' : '0.4';
                btn.style.borderColor = pdfView.highlightFilters[status] ? '#ffffff' : '#64748b';
            }
        });
    });
}

async function exportHighlightedPdf() {
    if (!pdfView.base) return;
    showToast('جاري تصدير PDF مع الشواهد...', 'info');
    try {
        const url = pdfView.base + '/export' + (pdfView.query || '');
        const response = await fetch(url);
        if (!response.ok) throw new Error('فشل التصدير');
        const blob = await response.blob();
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'document_highlighted.pdf';
        link.click();
        URL.revokeObjectURL(link.href);
        showToast('تم تنزيل PDF بنجاح', 'success');
    } catch (error) {
        showToast('فشل في تنزيل PDF: ' + error.message, 'error');
    }
}

// Inline PDF viewer for embedded report view
function showInlinePdfPage() {
    const image = document.getElementById('inline-pdf-image');
    if (!image) return;

    image.style.width = (pdfView.scale * 100) + '%';

    const numberEl = document.getElementById('inline-pdf-number');
    const totalEl = document.getElementById('inline-pdf-total');
    const prevBtn = document.getElementById('inline-pdf-prev');
    const nextBtn = document.getElementById('inline-pdf-next');

    if (numberEl) numberEl.value = pdfView.page;
    if (totalEl) totalEl.textContent = '/ ' + pdfView.count;
    if (prevBtn) prevBtn.disabled = pdfView.page <= 1;
    if (nextBtn) nextBtn.disabled = pdfView.page >= pdfView.count;

    image.onerror = () => showToast('تعذر عرض الصفحة', 'error');

    image.onload = async () => {
        const highlights = await loadPdfHighlights();
        renderInlinePdfHighlights(highlights);
        if (pdfView.targetEvidenceId) {
            const focused = focusHighlightByEvidenceId(pdfView.targetEvidenceId, 'inline-pdf-highlights-overlay');
            if (focused) pdfView.targetEvidenceId = null;
        }
    };
    image.src = pdfView.base + '/page' + (pdfView.query || '?') + (pdfView.query ? '&' : '') + 'page=' + pdfView.page;
}

function renderInlinePdfHighlights(highlights) {
    const image = document.getElementById('inline-pdf-image');
    if (!image) return;
    const container = image.parentElement;
    let overlay = document.getElementById('inline-pdf-highlights-overlay');

    if (!overlay) {
        overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        overlay.id = 'inline-pdf-highlights-overlay';
        overlay.style.cssText = 'position:absolute; top:0; left:0; cursor:pointer; pointer-events:auto;';
        if (container.style.position !== 'relative' && container.style.position !== 'absolute') {
            container.style.position = 'relative';
        }
        container.appendChild(overlay);
    }

    overlay.setAttribute('width', image.offsetWidth || image.width);
    overlay.setAttribute('height', image.offsetHeight || image.height);
    overlay.innerHTML = '';

    const imgWidth = image.offsetWidth || image.width;
    const imgHeight = image.offsetHeight || image.height;
    highlights.forEach((h, idx) => {
        if (!h.rect || h.rect.length < 4 || !shouldShowHighlight(h)) return;

        const [x0, y0, x1, y1] = h.rect;
        const coordinateWidth = Number(h.page_width) || ((image.naturalWidth || 1) / 1.25);
        const coordinateHeight = Number(h.page_height) || ((image.naturalHeight || 1) / 1.25);
        const scaleX = imgWidth / coordinateWidth;
        const scaleY = imgHeight / coordinateHeight;
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x0 * scaleX);
        rect.setAttribute('y', y0 * scaleY);
        rect.setAttribute('width', Math.max(1, (x1 - x0) * scaleX));
        rect.setAttribute('height', Math.max(1, (y1 - y0) * scaleY));
        rect.setAttribute('fill', h.color);
        rect.setAttribute('fill-opacity', '0.35');
        rect.setAttribute('stroke', 'none');
        rect.style.cursor = 'pointer';
        rect.style.transition = 'fill-opacity 0.15s';
        rect.title = `${h.status}: ${h.source_title}`;
        rect.dataset.highlightIndex = idx;
        rect.dataset.highlightData = JSON.stringify(h);

        rect.addEventListener('mouseover', () => {
            rect.setAttribute('fill-opacity', '0.55');
        });
        rect.addEventListener('mouseout', () => {
            if (rect.dataset.focused !== 'true') {
                rect.setAttribute('fill-opacity', '0.35');
            }
        });
        rect.addEventListener('click', (e) => {
            e.stopPropagation();
            focusHighlight(rect);
            showHighlightEvidence(h);
        });

        overlay.appendChild(rect);
    });
}

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
