# -*- coding: utf-8 -*-
"""
Updates CSS proportions, typography, and spacing for the login page in templates/index.html:
- Right panel: clamp(400px, 32.5vw, 640px) (~32.5% on 1920x1080)
- Form box: max-width 430px
- Logo: 84px
- Main heading: 28px
- Input height: 52px, font: 15.5px
- Button height: 54px, font: 16.5px
- Hero heading: 29px, description: 15.5px, features: 15px/13px
"""
from pathlib import Path
import os
import glob

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "templates" / "index.html"

css_start = "        /* ─── Split Screen Formal Institutional Login Gate ───────────────────────── */"
css_end = "        /* ─── Top Header Bar ─────────────────────────────────────────── */"

new_css = '''        /* ─── Split Screen Formal Institutional Login Gate ───────────────────────── */
        .login-screen-wrapper {
            position: fixed;
            inset: 0;
            z-index: 100000;
            display: flex;
            background: #ffffff;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            direction: rtl;
        }

        /* ── Right Section (Login Form: ~32.5% width, clamp(400px, 32.5vw, 640px)) ── */
        .login-form-side {
            flex: 0 0 clamp(400px, 32.5vw, 640px);
            width: clamp(400px, 32.5vw, 640px);
            background: #ffffff;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            padding: 44px 48px 24px 48px;
            box-sizing: border-box;
            overflow-y: auto;
            z-index: 3;
            box-shadow: -6px 0 28px rgba(15, 23, 42, 0.08);
            border-left: 1px solid var(--border-color);
        }

        .login-form-box {
            margin: auto 0;
            width: 100%;
            max-width: 430px;
        }

        .login-brand-header-center {
            text-align: center;
            margin-bottom: 28px;
        }

        .login-brand-logo-center {
            height: 84px;
            width: auto;
            object-fit: contain;
            margin: 0 auto 14px auto;
            display: block;
        }

        .login-brand-subheading {
            font-size: 15px;
            font-weight: 700;
            color: #1e3a8a;
            margin-bottom: 6px;
            line-height: 1.4;
        }

        .login-form-title-center {
            font-size: 28px;
            font-weight: 800;
            color: #0f2b5c;
            margin: 0 0 6px 0;
            letter-spacing: -0.3px;
            line-height: 1.3;
        }

        .login-form-subtitle-center {
            font-size: 14px;
            color: #64748b;
            font-weight: 600;
            margin-bottom: 12px;
            line-height: 1.4;
        }

        .login-badge-pill {
            display: inline-block;
            background: #f1f5f9;
            border: 1px solid #e2e8f0;
            color: #475569;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 16px;
            border-radius: 20px;
        }

        /* ── Login Form Fields ── */
        .login-field-group {
            margin-bottom: 20px;
            width: 100%;
        }

        .login-field-label {
            font-size: 14.5px;
            font-weight: 700;
            color: #0f2b5c;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            text-align: right;
        }

        .login-field-label svg {
            width: 17px;
            height: 17px;
            stroke: #0f2b5c;
        }

        .login-input-wrapper {
            position: relative;
            width: 100%;
        }

        .login-input-premium {
            width: 100%;
            height: 52px;
            border: 1.5px solid #cbd5e1;
            border-radius: 9px;
            padding: 0 16px;
            font-size: 15.5px;
            font-weight: 600;
            color: #0f2b5c;
            background: #ffffff;
            box-sizing: border-box;
            transition: all 0.18s ease;
            outline: none;
        }

        .login-input-premium::placeholder {
            color: #94a3b8;
            font-size: 14.5px;
            font-weight: 500;
        }

        .login-input-premium:focus {
            border-color: #0f2b5c;
            box-shadow: 0 0 0 3px rgba(15, 43, 92, 0.12);
            background: #ffffff;
        }

        .password-input-wrapper .login-input-premium {
            padding-left: 48px; /* Space for eye toggle button on the left in RTL */
        }

        .password-toggle-btn {
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            padding: 6px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #64748b;
            transition: color 0.15s ease;
        }

        .password-toggle-btn svg {
            width: 19px;
            height: 19px;
            stroke: #64748b;
        }

        .password-toggle-btn:hover {
            color: #0f2b5c;
        }

        .password-toggle-btn:focus {
            outline: 2px solid #2563eb;
        }

        .login-submit-btn-premium {
            width: 100%;
            height: 54px;
            background: #0f2b5c;
            color: #ffffff;
            border: none;
            border-radius: 9px;
            font-size: 16.5px;
            font-weight: 800;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-top: 24px;
            box-shadow: 0 4px 14px rgba(15, 43, 92, 0.22);
            transition: all 0.18s ease;
        }

        .login-submit-btn-premium svg {
            width: 20px;
            height: 20px;
            stroke: #ffffff;
        }

        .login-submit-btn-premium:hover {
            background: #1e3a8a;
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(15, 43, 92, 0.30);
        }

        .login-submit-btn-premium:active {
            transform: translateY(0);
        }

        .login-submit-btn-premium:disabled {
            opacity: 0.65;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .forgot-password-container {
            text-align: center;
            margin-top: 16px;
        }

        .forgot-password-btn {
            background: none;
            border: none;
            font-size: 14px;
            font-weight: 700;
            color: #2563eb;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 8px;
            border-radius: 4px;
            transition: color 0.15s ease;
        }

        .forgot-password-btn svg {
            width: 15px;
            height: 15px;
            stroke: #2563eb;
        }

        .forgot-password-btn:hover {
            color: #1d4ed8;
            text-decoration: underline;
        }

        .login-footer-institutional {
            text-align: center;
            border-top: 1px solid #f1f5f9;
            padding-top: 16px;
            margin-top: 24px;
            width: 100%;
        }

        .login-footer-copy {
            font-size: 12.5px;
            font-weight: 700;
            color: #64748b;
            margin-bottom: 4px;
            line-height: 1.4;
        }

        .login-footer-sub {
            font-size: 11.5px;
            font-weight: 600;
            color: #94a3b8;
            line-height: 1.4;
        }

        /* ── Left Section (Hero Background: flex 1 remaining width) ── */
        .login-hero-side {
            flex: 1;
            height: 100%;
            position: relative;
            background: url('/static/login.jpg') no-repeat center center;
            background-size: cover;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            padding: 56px 64px;
            box-sizing: border-box;
            color: #ffffff;
            overflow: hidden;
        }

        .login-hero-overlay {
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, 
                rgba(10, 30, 65, 0.12) 0%, 
                rgba(10, 30, 65, 0.32) 35%, 
                rgba(7, 22, 50, 0.68) 60%, 
                rgba(6, 18, 42, 0.90) 82%, 
                rgba(5, 14, 34, 0.97) 100%);
            z-index: 1;
        }

        .login-hero-content {
            position: relative;
            z-index: 2;
            max-width: 780px;
        }

        .login-hero-title {
            font-size: 29px;
            font-weight: 800;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            gap: 14px;
            margin: 0 0 14px 0;
            text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
            line-height: 1.3;
        }

        .hero-title-accent-bar {
            display: inline-block;
            width: 4.5px;
            height: 32px;
            background: #f59e0b; /* Gold accent */
            border-radius: 2px;
            flex-shrink: 0;
        }

        .login-hero-desc {
            font-size: 15.5px;
            line-height: 1.85;
            color: #e2e8f0;
            margin: 0 0 26px 0;
            font-weight: 500;
            max-width: 740px;
            text-shadow: 0 1px 6px rgba(0, 0, 0, 0.6);
        }

        .hero-features-row {
            display: flex;
            align-items: center;
            gap: 24px;
            max-width: 760px;
            border-top: 1px solid rgba(255, 255, 255, 0.15);
            padding-top: 22px;
        }

        .hero-feature-item {
            display: flex;
            align-items: center;
            gap: 14px;
            flex: 1;
        }

        .hero-feature-icon {
            width: 44px;
            height: 44px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.10);
            border: 1px solid rgba(255, 255, 255, 0.18);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            backdrop-filter: blur(4px);
        }

        .hero-feature-icon svg {
            width: 22px;
            height: 22px;
            stroke: #93c5fd;
        }

        .hero-feature-text {
            display: flex;
            flex-direction: column;
        }

        .hero-feature-title {
            font-size: 15px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.35;
            margin-bottom: 3px;
            text-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
        }

        .hero-feature-sub {
            font-size: 13px;
            color: #cbd5e1;
            line-height: 1.3;
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
        }

        .hero-feature-divider {
            width: 1px;
            height: 44px;
            background: rgba(255, 255, 255, 0.18);
            flex-shrink: 0;
        }

        /* ── Responsive Behavior ── */
        @media (max-width: 1024px) {
            .login-screen-wrapper {
                flex-direction: column-reverse;
                overflow-y: auto;
            }
            .login-form-side {
                width: 100%;
                max-width: 100%;
                min-width: unset;
                flex: unset;
                box-shadow: none;
                padding: 36px 24px;
            }
            .login-hero-side {
                width: 100%;
                min-height: 320px;
                flex: unset;
                padding: 36px 24px;
            }
            .hero-features-row {
                flex-direction: column;
                align-items: flex-start;
                gap: 14px;
            }
            .hero-feature-divider {
                display: none;
            }
        }
'''

content = INDEX_PATH.read_text(encoding='utf-8')

c_start_idx = content.find(css_start)
c_end_idx = content.find(css_end)
assert c_start_idx != -1 and c_end_idx != -1, "CSS region not found"

content = content[:c_start_idx] + new_css + "\n" + content[c_end_idx:]

INDEX_PATH.write_text(content, encoding='utf-8')
print("Successfully updated login proportions & typography in templates/index.html")

temp_dirs = glob.glob(os.path.join(os.environ['TEMP'], '_MEI*'))
updated_meis = 0
for d in temp_dirs:
    tmpl = Path(d) / 'templates' / 'index.html'
    if tmpl.exists():
        try:
            tmpl.write_text(content, encoding='utf-8')
            updated_meis += 1
        except Exception:
            pass

print(f"Updated live template in {updated_meis} unpacked temp directories!")
