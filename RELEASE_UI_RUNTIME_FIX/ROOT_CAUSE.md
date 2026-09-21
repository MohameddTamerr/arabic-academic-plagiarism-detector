# Root Cause Analysis: Packaged EXE UI Runtime Corruption (P1)

## 1. Executive Summary
During the manual launch of the packaged executable (`Arabic-Plagiarism-System.exe`), the runtime user interface exhibited visual corruption where report/source text, hover popovers ("اسم المصدر %0"), and datepicker navigation controls rendered underneath and leaked into the active Dashboard view.

A forensic investigation into the DOM hierarchy, CSS layout engine, PyInstaller asset pipeline, and browser runtime isolation confirmed **two interacting root causes** in `templates/index.html` and the PyInstaller numpy bundling specification.

Following surgical remediation without any visual redesign or backend/detector alterations, active view isolation has been 100% verified across both source runtime and the packaged standalone binary (`Arabic-Plagiarism-System-RC2.exe`) across multiple viewport resolutions (1920x1080 and 1366x768).

---

## 2. Root Cause Breakdown

### A. Unclosed HTML Tag Hierarchies in `templates/index.html`
1. **Unclosed Container in `view-upload` (Line 1260)**:
   - `<div class="content-constrained">` was opened inside `<section id="view-upload" ...>` but lacked a closing `</div>` prior to the closing `</section>`.
2. **Malformed Nesting in `view-help` (Line 2668)**:
   - Contains mismatched closing sequence `</section></div></section>`.
3. **Browser DOM Auto-Correction Cascade**:
   - Because standard HTML parsers encountered unbalanced closing tags within section blocks, the parser prematurely terminated `<main class="main-content">` and `.app-container`.
   - As a result, subsequent `<section>` views, floating popovers (`#hover-popover`, `#arabic-datepicker-popover`), and modal dialogs were ejected from the CSS Grid / Flexbox isolation of `<main>` and appended directly to the root `<body>` level.

### B. Unstyled Floating Popover Components in Normal Document Flow
1. **Floating Hover Popover (`#hover-popover`)**:
   - Element containing `"اسم المصدر %0"`, author snippet, and match metadata was declared directly in HTML without inline `style="display: none;"` and without corresponding `.hover-popover` CSS display/positioning rules in `<style>`.
   - Because it defaulted to `display: block` and `position: static`, once ejected outside `<main>`, it rendered as a physical block at the bottom right of the page regardless of which view was active.
2. **Datepicker Popover (`#arabic-datepicker-popover`)**:
   - The popover container lacked scoped `.arabic-datepicker-popover` position fixed/absolute styles and default `display: none`, causing navigation arrows and calendar widgets to participate in document layout.

### C. PyInstaller Submodule Collection for NumPy 2.x
- `tools/build_single_exe.py` bundled `--hidden-import=numpy` without `--collect-all=numpy` or explicit `numpy._core` hidden imports. Under Python 3.13 and NumPy 2.x, this prevented dynamic C-extension exception resolution (`numpy._core._exceptions`), which was resolved by adding `--collect-all=numpy` and explicit submodules.

---

## 3. Why Source and Packaged Assets Did Not Differ
- SHA-256 hash comparison between source files and the runtime PyInstaller extraction directory (`_MEI*`) confirmed that `templates/index.html`, `static/js/report-list.js`, and `static/js/pdf-viewer.js` were identical (0 hash divergence).
- The defect was intrinsic to the HTML/CSS markup contract in `templates/index.html` introduced during previous batch/health grid CSS changes, rather than stale asset bundling.

---

## 4. Why Automated Screenshots Did Not Catch It Previously
- Automated synthetic UI tests scrolled directly to targeted elements inside active views or evaluated specific viewport bounding boxes without asserting that the total page scroll height and document flow strictly equaled viewport height (`document.documentElement.scrollHeight == window.innerHeight`).
- Headless tests asserting `is_displayed()` on specific element IDs returned true for their parent section without checking whether sibling popover divs or unparented elements were rendering below the fold.

---

## 5. Surgical Remediation Applied

1. **`templates/index.html`**:
   - Cleanly closed `<div class="content-constrained">` in `view-upload`.
   - Cleanly balanced closing tags in `view-help`.
   - Verified with custom AST/stack tag validator: **0 tag mismatches**, all 17 view sections strictly contained inside `<main class="main-content">`.
   - Added robust CSS rules for `.hover-popover` and `.arabic-datepicker-popover`:
     ```css
     .hover-popover {
       display: none;
       position: fixed;
       z-index: 9999;
       max-width: 480px;
       pointer-events: none;
     }
     .arabic-datepicker-popover {
       display: none;
       position: absolute;
       z-index: 10000;
       max-width: 320px;
     }
     ```
   - Added inline `style="display: none;"` fallback to `#hover-popover` and `#arabic-datepicker-popover`.

2. **`tools/build_single_exe.py`**:
   - Added `--collect-all=numpy` and explicit `numpy._core` hidden imports to guarantee flawless standalone single-exe bundling.

---

## 6. Verification Results

| Dimension | Source Runtime Result | Packaged RC2 Binary Result | Status |
| :--- | :--- | :--- | :--- |
| **Visible Primary View Count** | Exactly 1 (`visibleCount=1`) | Exactly 1 (`visibleCount=1`) | PASS |
| **Horizontal Page Overflow** | `hScroll = false` | `hScroll = false` | PASS |
| **Leaked Content / Popovers** | None (`display: none; height: 0`) | None (`display: none; height: 0`) | PASS |
| **Targeted Test Suite** | 54 / 54 Passed | 54 / 54 Passed | PASS |
| **Full Pytest Regression** | 725 / 725 Passed (100%) | 725 / 725 Passed (100%) | PASS |
| **1920x1080 Viewport** | Verified (`after_source_1920.png`) | Verified (`after_exe_1920.png`) | PASS |
| **1366x768 Viewport** | Verified (`after_source_1366.png`) | Verified (`after_exe_1366.png`) | PASS |

---

## 7. Evidence Files Generated

All artifacts are preserved in `RELEASE_UI_RUNTIME_FIX/`:
- `before_actual_exe.png` — Baseline reproduction screenshot from broken EXE.
- `after_source_1920.png` — Repaired source runtime at 1920x1080.
- `after_source_1366.png` — Repaired source runtime at 1366x768.
- `after_exe_1920.png` — Packaged `Arabic-Plagiarism-System-RC2.exe` runtime at 1920x1080.
- `after_exe_1366.png` — Packaged `Arabic-Plagiarism-System-RC2.exe` runtime at 1366x768.
- `console_after.txt` — Browser runtime console logs.
- `resource_audit.txt` — Network and resource request audit.
- `view_visibility_audit.json` — Exhaustive DOM visibility, display, and bounding box state for all 17 views.
- `asset_hash_comparison.json` — Bit-for-bit SHA-256 asset hash comparison between source and packaged runtime.
