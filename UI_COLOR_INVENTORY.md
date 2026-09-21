# UI Visual Audit — Color Inventory & Palette Analysis
**System:** Arabic Academic Plagiarism Detection System (منظومة كشف الاستلال العلمي)  
**Inspection Date:** 2026-09-17  
**Scope:** Exhaustive CSS Custom Properties, Hex/RGB/RGBA Values, Gradients, and Semantic Color Roles  
**Audit Target:** Transition toward a formal, serious, calm, academic Arabic institutional aesthetic  

---

## 1. Primary & Brand Colors

| Color Token / Hex | RGB / RGBA | Where Used in Application | Current Purpose | Audit Status & Institutional Recommendation |
|---|---|---|---|---|
| `--primary-navy` (`#0f2b5c`) | `rgb(15, 43, 92)` | Main Header, Active Navigation Items, Primary Action Buttons, Brand Title | Primary institutional brand color | **KEEP** (Authoritative, serious dark navy suitable for academic police academy branding). |
| `--primary-dark` (`#0a1c3d`) | `rgb(10, 28, 61)` | Sidebar Background, Hero Overlay gradient | Dark background surface & contrast base | **KEEP** (Solid dark navy surface). |
| `--primary-hover` (`#163a7a`) | `rgb(22, 58, 122)` | Primary button hover state, Navigation hover | Interactive hover state | **KEEP** (Natural hover step). |
| `--active-item` (`#133366`) | `rgb(19, 51, 102)` | Sidebar active nav item highlight | Selected menu indicator | **KEEP** (Clear subtle distinction). |
| `#1e40af` / `#1d4ed8` | `rgb(30, 64, 175)` | Gradient stops, thesis completed badge, links | Secondary blue accent | **REVIEW CANDIDATE** (Replace multi-shade blue gradients with single solid navy accent). |
| `#0284c7` / `#0369a1` | `rgb(2, 132, 199)` | Stat card numbers, subheadings, links, tags | Sky blue accent | **REVIEW CANDIDATE** (Limit sky blue; use restrained dark navy for typography). |
| `#38bdf8` / `#60a5fa` | `rgb(56, 189, 248)` | Gradient icons, progressBar fills | Vibrant gradient accent | **REPLACE CANDIDATE** (Too bright / SaaS-like; replace with solid institutional navy). |

---

## 2. Background & Surface Neutrals

| Color Token / Hex | RGB / RGBA | Where Used in Application | Current Purpose | Audit Status & Institutional Recommendation |
|---|---|---|---|---|
| `--bg-main` (`#f8fafc`) | `rgb(248, 250, 252)` | App Body background, main content area | Global application background | **KEEP** (Clean, neutral off-white surface that reduces eye strain). |
| `--card-bg` (`#ffffff`) | `rgb(255, 255, 255)` | Cards, tables, modals, dropdown menus | Surface container background | **KEEP** (Crisp standard white surface). |
| `--border-color` (`#e2e8f0`)| `rgb(226, 232, 240)` | Card borders, table grid lines, input outlines | Structural separation | **KEEP** (Subtle, professional neutral border). |
| `--border-subtle` (`#f1f5f9`)| `rgb(241, 245, 249)` | Table header backgrounds, zebra rows | Secondary surface background | **KEEP** (Clean light gray for tabular data). |
| `#cbd5e1` | `rgb(203, 213, 225)` | Input focus borders, inactive icons | Medium gray border/icon | **KEEP** (Neutral UI element). |

---

## 3. Typography & Text Neutrals

| Color Token / Hex | RGB / RGBA | Where Used in Application | Current Purpose | Audit Status & Institutional Recommendation |
|---|---|---|---|---|
| `--text-dark` (`#0f172a`) | `rgb(15, 23, 42)` | Main body text, headings, table cell text | Primary typography | **KEEP** (High contrast, readable dark slate). |
| `--text-muted` (`#64748b`)| `rgb(100, 116, 139)` | Subtitles, helper text, timestamps, table headers | Secondary typography | **KEEP** (Calm neutral gray). |
| `#475569` | `rgb(71, 85, 105)` | Table labels, author names, descriptions | Medium text contrast | **KEEP** (Consistent neutral). |
| `#94a3b8` | `rgb(148, 163, 184)` | Placeholder text, disabled labels | Inactive typography | **KEEP** (Standard accessible placeholder). |

---

## 4. Semantic Status Colors (Strict Status Use Only)

| Color Token / Hex | RGB / RGBA | Where Used in Application | Current Purpose | Audit Status & Institutional Recommendation |
|---|---|---|---|---|
| `--green-ok` (`#10b981` / `#059669`)| `rgb(16, 185, 129)` | Final accept status, approved badges, low risk | Success / Approved status | **KEEP (STATUS ONLY)** (Retain exclusively for approved/accepted status; do not use decoratively). |
| `--green-bg` (`#ecfdf5` / `#dcfce7`)| `rgb(236, 253, 245)` | Background of success toasts and accepted badges | Soft status pill background | **KEEP** (Clean accessible tint for status). |
| `--red-copy` (`#ef4444` / `#dc2626`)| `rgb(239, 68, 68)` | Direct copy match highlight, reject badges, error alert | High similarity / Danger / Rejected | **KEEP (STATUS ONLY)** (Restrain strictly for matched plagiarized text and reject actions). |
| `--red-bg` (`#fee2e2` / `#fef2f2`)| `rgb(254, 226, 226)` | Error banners, high risk verdict background | Error / Danger alert background | **KEEP** (Standard error container tint). |
| `--orange-para` (`#f97316` / `#d97706`)| `rgb(249, 115, 22)` | Paraphrase match highlight, medium risk alerts | Paraphrase / Warning / Pending | **KEEP (STATUS ONLY)** (Use calm institutional amber `#d97706` rather than neon orange). |
| `--orange-bg` (`#ffedd5` / `#fef3c7`)| `rgb(255, 237, 213)` | Warning toast background, pending status badge | Warning background | **KEEP** (Standard warning tint). |
| `--purple-ai` (`#8b5cf6` / `#7c3aed`)| `rgb(139, 92, 246)` | AI similarity indicators, schema version tag | AI detection metric badge | **REPLACE CANDIDATE** (Purple accent looks like generic AI/SaaS template; replace with dark slate or navy). |
| `--purple-bg` (`#f3e8ff` / `#eef2ff`)| `rgb(243, 232, 255)` | Background for AI badges | AI tag container | **REPLACE CANDIDATE** (Replace with standard institutional neutral gray tag `#f1f5f9`). |

---

## 5. Gradients & Multi-Tone Visual Patterns

| Gradient Definition | CSS Rule / Location | Visual Effect | Audit Status & Institutional Recommendation |
|---|---|---|---|
| `linear-gradient(135deg, #0f2b5c 0%, #1e40af 100%)` | `.hero-welcome`, `.login-brand-header` | Multi-color blue hero header | **REPLACE CANDIDATE** (Replace with solid dark navy background `#0f2b5c`). |
| `linear-gradient(90deg, #0284c7, #60a5fa)` | `.blue-gradient` stat card icon background | Startup SaaS vibrant icon background | **REPLACE CANDIDATE** (Replace with solid subtle navy tint `#e0f2fe`). |
| `linear-gradient(90deg, #059669, #34d399)` | `.emerald-gradient` stat card icon background | Bright green gradient icon background | **REPLACE CANDIDATE** (Replace with solid subtle gray or navy icon container). |
| `linear-gradient(90deg, #4f46e5, #818cf8)` | `.indigo-gradient` stat card icon background | Startup SaaS purple-indigo gradient | **REPLACE CANDIDATE** (Remove multi-color icon gradients entirely). |
| `linear-gradient(135deg, #fff1f2, #fee2e2)` | `#risk-verdict-banner` (High risk state) | Pink-red gradient warning banner | **REPLACE CANDIDATE** (Replace with clean flat alert box with solid border). |
| `linear-gradient(135deg, #ecfdf5, #d1fae5)` | `#risk-verdict-banner` (Safe risk state) | Light green gradient banner | **REPLACE CANDIDATE** (Replace with clean flat institutional card). |
| `linear-gradient(135deg, #fffbeb, #fef3c7)` | `#risk-verdict-banner` (Review state) | Yellow-amber gradient banner | **REPLACE CANDIDATE** (Replace with clean flat institutional card). |

---

## 6. Visual Target Palette Summary (For Future Reference — DO NOT APPLY YET)

- **Primary Base:** Dark Institutional Navy (`#0f2b5c` / `#0a1c3d`).
- **Main Surfaces:** Off-white (`#f8fafc`) and Pure White (`#ffffff`).
- **Borders & Dividers:** Crisp Neutral Gray (`#e2e8f0` / `#cbd5e1`).
- **Typography:** Deep Slate (`#0f172a`) for titles/body, Slate Gray (`#64748b`) for metadata.
- **Semantic Badges (Status Only):**
  - Accepted / Success: Forest Green (`#059669` text on `#ecfdf5` background).
  - High Risk / Danger / Rejected: Crimson Red (`#dc2626` text on `#fee2e2` background).
  - Pending / Warning: Warm Amber (`#d97706` text on `#fef3c7` background).
  - Cited / Safe: Slate Blue (`#0369a1` text on `#f0f9ff` background).
- **Eliminate:** All neon cyan, purple SaaS accents, multi-color icon gradients, and glassmorphic blur filters.
