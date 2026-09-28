# Project Overview
- **Arabic Academic Plagiarism Detector**: A 100% offline Arabic academic plagiarism detection, citation verification, and institutional integrity management system.
- **Tech Stack**: Python 3.10+, Flask (App Factory & Blueprints), Waitress (offline WSGI server), SQLAlchemy 2.0 (SQLite default, PostgreSQL supported), PyMuPDF (fitz) + pypdf + docx + pytesseract (OCR), scikit-learn (TF-IDF, n-grams), difflib (SequenceMatcher), Vanilla JS/HTML5/CSS Single-Page App (SPA).
- **Startup**: `python main.py` or `python run_app.py` or `python server.py` (hosts on `http://127.0.0.1:5000`).

# Architecture
- **Backend**: Flask application factory (`app/__init__.py`), modular route Blueprints (`app/routes/`), business service layer (`app/services/`), data repository layer (`app/repositories/`).
- **Frontend**: Single-page application embedded in `templates/index.html` with modular scripts in `static/js/` (`pdf-viewer.js`, `report-list.js`).
- **Database**: SQLAlchemy models in `app/models/` (`schema.py`, `research_schema.py`, `audit_schema.py`, `queue_schema.py`). Default local SQLite at `Data/Database/papers.db` (`config.py:DEFAULT_SQLITE_PATH`).
- **Detection Engine**: Multi-stage pipeline under `plagiarism_detector/` (preprocessing, shingle matching, TF-IDF matching, citation & bibliography filtering, page allowance).
- **PDF/OCR System**: Document text extraction via PyMuPDF/pypdf and fallback OCR via pytesseract (`plagiarism_detector/extraction/`), rendered via PyMuPDF pixmaps (`app/routes/pdf_routes.py`).
- **Report System**: Deterministic report generation (`plagiarism_detector/reporting/report_builder.py`), SHA-256 tamper-evident integrity snapshots (`app/services/report_integrity_service.py`), HTML/PDF/DOCX exports (`plagiarism_detector/reporting/html_exporter.py`).

# Main Flow
- **PDF Upload**: `app/routes/scan_routes.py:scan_file()` / `app/routes/paper_routes.py:upload_paper()` -> validates via `app/services/upload_validation_service.py:validate_uploaded_file()`.
- **Extraction/OCR**: `app/services/scan_service.py:_execute_scan_pipeline()` -> `plagiarism_detector/extraction/page_extractor.py:extract_document_pages()` (PyMuPDF `page.get_text()`, fallback `ocr_engine.py:ocr_page_pixmap()`).
- **Arabic Preprocessing**: `plagiarism_detector/reporting/report_builder.py:analyze_academic_document()` -> `plagiarism_detector/preprocessing/cheating_detector.py:clean_cheating_text()`, `normalizer.py:normalize_light()` / `normalize_aggressive()`, `segmenter.py:segment_pages()`.
- **Detection**: `report_builder.py:analyze_academic_document()` -> filters common phrases (`filters/common_phrases.py:filter_common_spans()`), checks citations (`citations/citation_detector.py:detect_citation()`), retrieves candidates (`detection/candidate_retriever.py:CandidateRetriever`), runs Shingle/Jaccard (`detection/shingle_matcher.py:match_exact_or_near_copy()`), runs TF-IDF (`detection/tfidf_matcher.py:match_lexical_paraphrase()`).
- **Similarity Calculation**: `report_builder.py:analyze_academic_document()` -> filters bibliography (`citations/bibliography_detector.py:filter_bibliography_sections()`), calculates percentage metrics (copied, paraphrased, cited, problematic, overall), evaluates page limits (`reporting/page_allowance.py:compute_source_allowance()`).
- **Evidence Generation**: `report_builder.py:analyze_academic_document()` builds segment items -> structured into frozen evidence lists in `app/services/report_integrity_service.py:_extract_sources_and_evidence()`.
- **Database Storage**: `app/repositories/report_repo.py:save_report()` writes `LegacyReport` (`reports` table: `report_json`, `evidence_snapshot_json`) and links `Research` / `ResearchFile` via `app/repositories/batch_repo.py`.
- **Report API**: `app/routes/report_routes.py`: `get_report_details_route()` (`GET /api/reports/<id>`), `get_report_evidence_route()` (`GET /api/reports/<id>/evidence`), `get_report_sources_route()` (`GET /api/reports/<id>/sources`), `get_report_page_evidence_route()` (`GET /api/reports/<id>/page_evidence`).
- **Frontend Report**: `templates/index.html`: `loadReport()`, `loadReportEvidence()`, `renderEvidenceCards()`, `renderReportDetails()`.

# Important Files
| File | Purpose | Important functions/classes |
| --- | --- | --- |
| `config.py` | Central configuration, thresholds, storage paths | `DEFAULT_SETTINGS`, `DATABASE_URL`, `STORAGE_ROOT`, `MAX_CONCURRENT_SCANS` |
| `server.py` / `main.py` | Server entry points (Waitress WSGI & dev runner) | `create_app()`, `run_production_server()` |
| `app/__init__.py` | Flask app factory, Blueprint registration, DB init | `create_app()` |
| `app/routes/report_routes.py` | Report, evidence, sources, decision & export routes | `get_report_details_route()`, `get_report_evidence_route()`, `export_report_pdf_route()` |
| `app/routes/scan_routes.py` | Document submission & scan task polling API | `scan_file()`, `get_scan_status_route()` |
| `app/routes/pdf_routes.py` | Authenticated offline PDF page pixmap & info streaming | `view_pdf()`, `_resolve()` |
| `app/routes/paper_routes.py` | Reference document catalog & dashboard stats API | `get_stats()`, `list_papers()`, `upload_paper()` |
| `app/services/scan_service.py` | Background scan orchestration & pipeline execution | `start_async_scan()`, `_execute_scan_pipeline()`, `start_thesis_scan()` |
| `app/services/report_integrity_service.py` | Report revisions, tamper hashes, evidence extraction | `create_report_revision()`, `finalize_report()`, `_extract_sources_and_evidence()` |
| `app/repositories/report_repo.py` | Persistence, pagination & filtering of reports/evidence | `save_report()`, `get_report()`, `get_report_evidence_paginated()` |
| `app/models/schema.py` | Primary ORM models (reports, documents, jobs, users) | `LegacyReport`, `Document`, `DocumentPage`, `DocumentSegment`, `JobRecord` |
| `app/models/research_schema.py` | Thesis, multi-file research & batch ORM models | `Research`, `ResearchFile`, `Thesis`, `ThesisPart`, `ScanBatch` |
| `plagiarism_detector/reporting/report_builder.py` | Academic report builder & detection pipeline core | `analyze_academic_document()`, `build_pipeline_index()`, `get_pipeline_index()` |
| `plagiarism_detector/detection/shingle_matcher.py` | Word shingle & Jaccard exact matching (Stage A) | `match_exact_or_near_copy()`, `jaccard_similarity()`, `sequence_ratio()` |
| `plagiarism_detector/detection/tfidf_matcher.py` | TF-IDF & cosine similarity lexical paraphrase (Stage B) | `match_lexical_paraphrase()` |
| `plagiarism_detector/detection/candidate_retriever.py` | Inverted index & shingle/token candidate retrieval | `CandidateRetriever`, `retrieve_candidates()`, `retrieve_candidates_for_shingles()` |
| `plagiarism_detector/extraction/page_extractor.py` | Page-level text extraction from PDF/DOCX/TXT | `extract_document_pages()`, `_extract_pages_from_pdf()`, `pdf_text_needs_ocr()` |
| `plagiarism_detector/extraction/ocr_engine.py` | Tesseract OCR engine wrapper with language check | `ocr_page_pixmap()`, `check_ocr_availability()` |
| `plagiarism_detector/citations/citation_detector.py` | Academic citation & quotation detector | `detect_citation()`, `detect_citation_refined()` |
| `plagiarism_detector/citations/bibliography_detector.py` | Bibliography & reference section boundary detector | `filter_bibliography_sections()`, `is_bibliography_header()` |
| `templates/index.html` | Frontend SPA containing UI, views, styles, and scripts | `loadReport()`, `loadReportEvidence()`, `renderEvidenceCards()`, `openInternalPdf()` |
| `static/js/pdf-viewer.js` | Modal PDF viewer & text highlighting helper | `openInternalPdf()`, `showPdfPage()`, `literalEvidence()` |

# Detection System
- **Exact matching**: `plagiarism_detector/detection/shingle_matcher.py:match_exact_or_near_copy()` using `SequenceMatcher` (sequence ratio threshold >= 0.65).
- **Shingles/Jaccard**: `plagiarism_detector/preprocessing/normalizer.py:get_shingles()` (default size = 4 words) & `shingle_matcher.py:jaccard_similarity()` (default threshold = 0.33).
- **TF-IDF**: `plagiarism_detector/detection/tfidf_matcher.py:match_lexical_paraphrase()` (word n-grams 1-2 + char_wb 3-4, cosine threshold = 0.35/0.60).
- **Semantic/Paraphrase detection**: `plagiarism_detector/detection/semantic_matcher.py:match_semantic_similarity()` (optional, controlled by `DEFAULT_SETTINGS['enable_semantic_model'] = False`); stylistic analysis in `plagiarism_detector/ai_analysis/stylistic_indicators.py:analyze_stylistic_ai_indicators()`.
- **Citations**: `plagiarism_detector/citations/citation_detector.py:detect_citation()` (detects `«...»`, `[1]`, author-year, attribution verbs; refines out dates/laws via `_is_valid_author_refined()`).
- **Bibliography exclusion**: `plagiarism_detector/citations/bibliography_detector.py:filter_bibliography_sections()` (identifies headers like "المراجع والمصادر" or regex bib entries; marks `is_bibliography=True`).
- **Final score calculation** (`report_builder.py:analyze_academic_document()`):
  - `clean_total_words` = total words minus words in segments marked `is_bibliography`.
  - `matched_total_words` = `copied_words` + `paraphrased_words` + `cited_words`.
  - `problematic_words` = `copied_words` + `paraphrased_words` (un-cited matches).
  - `overall_pct` = `min(round((matched_total_words / clean_total_words) * 100, 1), 100.0)`
  - `problematic_pct` = `min(round((problematic_words / clean_total_words) * 100, 1), overall_pct)`
  - `copied_pct` = `round((copied_words / clean_total_words) * 100, 1)`
  - `paraphrase_pct` = `round((paraphrased_words / clean_total_words) * 100, 1)`
  - `cited_pct` = `round((cited_words / clean_total_words) * 100, 1)`

# Evidence System
- **Detection Result**: `report_builder.py:analyze_academic_document()` produces `segments` list (each segment contains `text`, `page_number`, `source_id`, `source_title`, `source_page`, `matched_text`, `status`, `match_type`, `is_cited`).
- **Evidence Creation**: `app/services/report_integrity_service.py:_extract_sources_and_evidence()` extracts matches into sorted `evidence` items.
- **Storage**: `app/repositories/report_repo.py:save_report()` serializes into `reports` table (`reports.report_json` & `reports.evidence_snapshot_json`).
- **API Endpoint**: `GET /api/reports/<report_id>/evidence` (`app/routes/report_routes.py:get_report_evidence_route()`) with pagination, filters (`match_type`, `min_pct`, `q`, `part_id`, `source_id`), implemented in `report_repo.py:get_report_evidence_paginated()`.
- **Frontend Request**: `templates/index.html:loadReportEvidence(page)` fetches `/api/reports/${currentReportId}/evidence?...`.
- **UI Rendering**: `templates/index.html:renderEvidenceCards(data)` dynamically renders evidence comparison cards using `static/js/pdf-viewer.js:literalEvidence()` for highlighted token overlap.

# PDF System
- **Upload**: `app/routes/scan_routes.py:scan_file()` or thesis upload endpoints save files to `Data/Storage/temp_uploads` or research folder.
- **Extraction**: `plagiarism_detector/extraction/page_extractor.py:extract_document_pages()` processes page-by-page with PyMuPDF.
- **OCR**: `plagiarism_detector/extraction/ocr_engine.py:ocr_page_pixmap()` invokes Tesseract if page is empty or text layer is corrupted.
- **Page Information**: Tracked per page in `DocumentPage.page_number` and per segment in `DocumentSegment.page_number` (1-indexed).
- **PDF Viewer**: Modal in `templates/index.html` + `static/js/pdf-viewer.js` (`openInternalPdf()`), which streams PNG page images from `app/routes/pdf_routes.py:view_pdf()` (`/api/pdf/<kind>/<record_id>/page?page=N`).
- **Coordinates/Offsets**: Not currently stored; `/api/pdf/.../info` returns `coordinates_available=False`.
- **PDF Report Export**: `plagiarism_detector/reporting/html_exporter.py` / `app/routes/report_routes.py:export_report_pdf_route()`.
- **Data Supporting Future Text Highlighting**:
  - `DocumentSegment.page_number`, `DocumentSegment.raw_text`, and `matched_text` in report segments.
  - PyMuPDF (`fitz`) `page.search_for(segment_text)` or `page.get_text("words")` can dynamically compute bounding box rectangles for on-image highlight rendering or vector overlay.

# Reports & Dashboard
- **Backend Routes**: `app/routes/report_routes.py`, `app/routes/paper_routes.py`, `app/routes/thesis_routes.py`, `app/routes/batch_routes.py`.
- **API Endpoints**: `/api/reports`, `/api/reports/<id>`, `/api/reports/<id>/evidence`, `/api/reports/<id>/sources`, `/api/reports/<id>/page_evidence`, `/api/reports/<id>/export/<format>`, `/api/reports/<id>/review_decision`, `/api/stats`, `/api/theses`, `/api/batch`.
- **Templates**: `templates/index.html`.
- **JavaScript**: `templates/index.html` (main SPA logic), `static/js/pdf-viewer.js`, `static/js/report-list.js`.
- **Statistics**: `app/routes/paper_routes.py:get_stats()`, computed via `app/repositories/report_repo.py:get_reports_stats()` and `document_repo.py:get_document_count()`.
- **Filters**: Status, category, search query in repository queries (`document_repo.py`, `report_repo.py`).
- **Export**: PDF (`/api/reports/<id>/export/pdf`), HTML (`/api/reports/<id>/export/html`), Word DOCX (`/api/reports/<id>/export/word`).

# Database
- **`documents` (`Document`)**: Reference works (file hash, title, author, year, status). Has many `document_pages` and `document_segments`.
- **`document_pages` (`DocumentPage`)**: Raw and normalized text per page (`document_id`, `page_number`, `raw_text`).
- **`document_segments` (`DocumentSegment`)**: Segmented sentences/paragraphs for inverted indexing (`document_id`, `page_number`, `segment_number`, `raw_text`, `word_count`).
- **`reports` (`LegacyReport`)**: Plagiarism scan reports (`id`, `title`, `author`, `overall_pct`, `copied_pct`, `para_pct`, `report_json`, `evidence_snapshot_json`, `research_id`, `artifact_status`, `finalization_hash`).
- **`research` (`Research`)**: Multi-file thesis or research entity (`reference_number`, `title`, `author`, `batch_id`, `report_id`, `scan_status`, `review_status`). Has many `research_files`.
- **`research_files` (`ResearchFile`)**: Files belonging to a research entity (`research_id`, `original_filename`, `file_path`, `file_order`, `file_hash`).
- **`scan_batches` (`ScanBatch`) & `scan_batch_items` (`ScanBatchItem`)**: Multi-item batch scans linked to research entities.
- **`theses` (`Thesis`) & `thesis_parts` (`ThesisPart`)**: Thesis entities and part-by-part decomposition with independent scans.
- **`job_records` (`JobRecord`) & `scan_jobs` (`ScanJob`)**: Background task tracking, status, priority, and progress.
- **`audit_logs` (`AuditLog`)**: Immutable institutional audit trail (`event_id`, `action`, `category`, `user_id`, `research_id`, `created_at`).
- **`users` (`User`) & `auth_lockouts` (`AuthLockout`)**: User accounts, RBAC roles, and login lockout state.

# Dates
- **Created**: Models use `default=datetime.utcnow` (naive UTC); `scan_service.py` uses `datetime.datetime.now().strftime('%Y-%m-%d %H:%M')` (local time string).
- **Stored**: SQLite stores datetimes as naive text/timestamp columns; JSON blobs store `YYYY-MM-DD HH:MM` strings.
- **Formatted & Displayed**: Repositories format via `.strftime('%Y-%m-%d %H:%M')`; frontend renders raw string values directly.
- **Timezone Handling**: No explicit timezone conversion layer exists; server local time and UTC are mixed.

# Run & Test Commands
- **Run Application (Waitress WSGI)**: `python main.py` or `python run_app.py` or `python server.py`
- **Run Application (Explicit Flask Dev)**: `$env:FLASK_ENV="development"; python main.py --dev`
- **Run All Tests**: `pytest`
- **Run Specific Test File**: `pytest tests/test_detection.py` or `pytest tests/test_report_integrity.py`
- **Run Keyword-Filtered Tests**: `pytest -k "test_evidence or test_citation"`

# Known Issues / Planned Work
- Evidence may remain stuck on "جاري تحميل الشواهد..."
- Paraphrasing may show a percentage such as 7% while report counters show 0
- Need PDF text highlights
- Need evidence ↔ PDF highlight navigation
- Need downloadable PDF with persistent highlights
- Dates/time are inconsistent
- Need Today / Weekly / Monthly / Custom date filters
- Dashboard statistics should follow filters
- Report UI/UX needs improvement
- Detection accuracy needs validation
- Citation/bibliography exclusion needs validation
- Source attribution needs validation
- Loading/error/empty states need review
- Performance with many sources needs review

# Instructions for Claude Code
- Read CLAUDE.md FIRST.
- Do not rescan the whole project unless absolutely necessary.
- Work task-by-task.
- Search before opening large files.
- Open only files relevant to the current task.
- Prefer targeted snippets over entire files.
- Do not inspect venv, generated files, uploads or datasets unless required.
- Make minimal changes.
- Do not refactor unrelated code.
- Run targeted tests first.
- Preserve working functionality.
- Update CLAUDE.md only when architecture actually changes.
- Never assume a file/function/endpoint exists; verify it when needed.
