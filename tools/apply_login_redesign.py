# -*- coding: utf-8 -*-
"""
Applies the premium institutional login page redesign to templates/index.html:
- Split screen: 69% Left hero section (authentic Police Academy photograph with dark navy gradient, gold accent title, and 3 horizontal features)
- 31% Right section (pure white, official Academy logo, centered institutional typography, pill badge)
- Form inputs: 50px height, rounded corners, icons, password visibility toggle (Eye button)
- Primary button: 52px height, deep navy, professional login icon
- Forgot password link: Centered, blue
- Preserves all authentication logic, CSRF tokens, session storage, error alerts, and first-time setup modal.
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

        /* ── Right Section (Login Form: ~31% width) ── */
        .login-form-side {
            width: 31%;
            min-width: 380px;
            max-width: 480px;
            background: #ffffff;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            padding: 40px 36px 24px 36px;
            box-sizing: border-box;
            overflow-y: auto;
            z-index: 3;
            box-shadow: -4px 0 25px rgba(15, 23, 42, 0.06);
            border-left: 1px solid var(--border-color);
        }

        .login-form-box {
            margin: auto 0;
            width: 100%;
            max-width: 360px;
        }

        .login-brand-header-center {
            text-align: center;
            margin-bottom: 24px;
        }

        .login-brand-logo-center {
            height: 78px;
            width: auto;
            object-fit: contain;
            margin: 0 auto 12px auto;
            display: block;
        }

        .login-brand-subheading {
            font-size: 13.5px;
            font-weight: 700;
            color: #1e3a8a;
            margin-bottom: 4px;
        }

        .login-form-title-center {
            font-size: 26px;
            font-weight: 800;
            color: #0f2b5c;
            margin: 0 0 4px 0;
            letter-spacing: -0.3px;
        }

        .login-form-subtitle-center {
            font-size: 13px;
            color: #64748b;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .login-badge-pill {
            display: inline-block;
            background: #f1f5f9;
            border: 1px solid #e2e8f0;
            color: #475569;
            font-size: 11.5px;
            font-weight: 700;
            padding: 3px 14px;
            border-radius: 20px;
        }

        /* ── Login Form Fields ── */
        .login-field-group {
            margin-bottom: 16px;
            width: 100%;
        }

        .login-field-label {
            font-size: 13.5px;
            font-weight: 700;
            color: #0f2b5c;
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
            text-align: right;
        }

        .login-input-wrapper {
            position: relative;
            width: 100%;
        }

        .login-input-premium {
            width: 100%;
            height: 50px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 0 14px;
            font-size: 14px;
            font-weight: 600;
            color: #0f2b5c;
            background: #ffffff;
            box-sizing: border-box;
            transition: all 0.18s ease;
            outline: none;
        }

        .login-input-premium:focus {
            border-color: #0f2b5c;
            box-shadow: 0 0 0 3px rgba(15, 43, 92, 0.12);
            background: #ffffff;
        }

        .password-input-wrapper .login-input-premium {
            padding-left: 44px; /* Space for the eye button on the left in RTL */
        }

        .password-toggle-btn {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            padding: 6px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #64748b;
            transition: color 0.15s ease;
        }

        .password-toggle-btn:hover {
            color: #0f2b5c;
        }

        .password-toggle-btn:focus {
            outline: 2px solid #2563eb;
        }

        .login-submit-btn-premium {
            width: 100%;
            height: 52px;
            background: #0f2b5c;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-size: 15.5px;
            font-weight: 800;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-top: 18px;
            box-shadow: 0 4px 12px rgba(15, 43, 92, 0.2);
            transition: all 0.18s ease;
        }

        .login-submit-btn-premium:hover {
            background: #1e3a8a;
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(15, 43, 92, 0.28);
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
            margin-top: 14px;
        }

        .forgot-password-btn {
            background: none;
            border: none;
            font-size: 13px;
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

        .forgot-password-btn:hover {
            color: #1d4ed8;
            text-decoration: underline;
        }

        .login-footer-institutional {
            text-align: center;
            border-top: 1px solid #f1f5f9;
            padding-top: 14px;
            margin-top: 20px;
            width: 100%;
        }

        .login-footer-copy {
            font-size: 11.5px;
            font-weight: 700;
            color: #64748b;
            margin-bottom: 2px;
        }

        .login-footer-sub {
            font-size: 10.5px;
            font-weight: 600;
            color: #94a3b8;
        }

        /* ── Left Section (Hero Background: ~69% width) ── */
        .login-hero-side {
            flex: 1;
            width: 69%;
            height: 100%;
            position: relative;
            background: url('/static/login.jpg') no-repeat center center;
            background-size: cover;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            padding: 48px 60px;
            box-sizing: border-box;
            color: #ffffff;
            overflow: hidden;
        }

        .login-hero-overlay {
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, 
                rgba(10, 30, 65, 0.18) 0%, 
                rgba(10, 30, 65, 0.38) 35%, 
                rgba(7, 22, 50, 0.72) 60%, 
                rgba(6, 18, 42, 0.92) 85%, 
                rgba(5, 14, 34, 0.98) 100%);
            z-index: 1;
        }

        .login-hero-content {
            position: relative;
            z-index: 2;
            max-width: 720px;
        }

        .login-hero-title {
            font-size: 26px;
            font-weight: 800;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            gap: 12px;
            margin: 0 0 12px 0;
            text-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
        }

        .hero-title-accent-bar {
            display: inline-block;
            width: 4px;
            height: 26px;
            background: #f59e0b; /* Gold accent */
            border-radius: 2px;
            flex-shrink: 0;
        }

        .login-hero-desc {
            font-size: 13.5px;
            line-height: 1.8;
            color: #cbd5e1;
            margin: 0 0 22px 0;
            font-weight: 500;
            max-width: 650px;
            text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
        }

        .hero-features-row {
            display: flex;
            align-items: center;
            gap: 20px;
            max-width: 680px;
            border-top: 1px solid rgba(255, 255, 255, 0.12);
            padding-top: 18px;
        }

        .hero-feature-item {
            display: flex;
            align-items: center;
            gap: 10px;
            flex: 1;
        }

        .hero-feature-icon {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .hero-feature-icon svg {
            width: 18px;
            height: 18px;
            stroke: #93c5fd;
        }

        .hero-feature-text {
            display: flex;
            flex-direction: column;
        }

        .hero-feature-title {
            font-size: 13px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.35;
            margin-bottom: 2px;
        }

        .hero-feature-sub {
            font-size: 11px;
            color: #94a3b8;
            line-height: 1.3;
        }

        .hero-feature-divider {
            width: 1px;
            height: 34px;
            background: rgba(255, 255, 255, 0.16);
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
                box-shadow: none;
                padding: 30px 20px;
            }
            .login-hero-side {
                width: 100%;
                min-height: 300px;
                flex: unset;
                padding: 30px 20px;
            }
            .hero-features-row {
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
            }
            .hero-feature-divider {
                display: none;
            }
        }
'''

html_start = '    <!-- ─── Full-Screen Login Gate (First thing that appears on open) ────── -->'
html_end = '    <!-- ─── Mandatory employee first-login setup ──────────────────────── -->'

new_html = '''    <!-- ─── Full-Screen Login Gate (First thing that appears on open) ────── -->
    <!-- ─── Full-Screen Modern Split Login Gate ────────────────────────── -->
    <div id="login-screen" class="login-screen-wrapper">
        <!-- Right / Form Side (31% width, white) -->
        <div class="login-form-side">
            <div class="login-form-box">
                <!-- Branding Header (Centered) -->
                <div class="login-brand-header-center">
                    <img src="/static/logo.png" alt="شعار أكاديمية الشرطة" class="login-brand-logo-center">
                    <div class="login-brand-subheading">أكاديمية الشرطة — كلية الدراسات العليا</div>
                    <h2 class="login-form-title-center" id="login-title-heading">نظام كشف الاستلال العلمي</h2>
                    <div class="login-form-subtitle-center" id="login-subtitle-heading">تسجيل الدخول الآمن للمنظومة الأكاديمية</div>
                    <div class="login-badge-pill">(تشغيل محلي بالكامل)</div>
                </div>

                <!-- Error Alert Box -->
                <div id="login-error-alert" style="display: none; background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 10px 14px; border-radius: 8px; font-size: 12.5px; font-weight: 700; margin-bottom: 16px; align-items: center; gap: 8px;">
                    <svg class="nav-icon-svg" style="width:16px; height:16px; stroke:#991b1b; flex-shrink: 0;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <span id="login-error-text">اسم المستخدم أو كلمة المرور غير صحيحة</span>
                </div>

                <!-- Standard Login Form -->
                <form id="form-login-standard" onsubmit="event.preventDefault(); submitLogin();">
                    <div class="login-field-group">
                        <label class="login-field-label" for="login-username">
                            <svg class="nav-icon-svg" style="width:15px; height:15px; stroke:#0f2b5c;" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                            <span>اسم المستخدم:</span>
                        </label>
                        <div class="login-input-wrapper">
                            <input type="text" id="login-username" class="login-input-premium" placeholder="أدخل اسم المستخدم..." autocomplete="username" autofocus>
                        </div>
                    </div>

                    <div class="login-field-group">
                        <label class="login-field-label" for="login-password">
                            <svg class="nav-icon-svg" style="width:15px; height:15px; stroke:#0f2b5c;" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                            <span>كلمة المرور:</span>
                        </label>
                        <div class="login-input-wrapper password-input-wrapper">
                            <input type="password" id="login-password" class="login-input-premium" placeholder="••••••••" autocomplete="current-password">
                            <button type="button" id="btn-toggle-password-visibility" class="password-toggle-btn" onclick="togglePasswordVisibility()" aria-label="إظهار / إخفاء كلمة المرور" tabindex="0">
                                <svg id="eye-icon-open" class="nav-icon-svg" style="width: 17px; height: 17px; stroke: #64748b;" viewBox="0 0 24 24">
                                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                    <circle cx="12" cy="12" r="3"></circle>
                                </svg>
                                <svg id="eye-icon-closed" class="nav-icon-svg" style="width: 17px; height: 17px; stroke: #64748b; display: none;" viewBox="0 0 24 24">
                                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                                    <line x1="1" y1="1" x2="23" y2="23"></line>
                                </svg>
                            </button>
                        </div>
                    </div>

                    <button type="submit" id="btn-login-submit" class="login-submit-btn-premium">
                        <span>تسجيل الدخول</span>
                        <svg class="nav-icon-svg" style="width:18px; height:18px; stroke:white;" viewBox="0 0 24 24">
                            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                            <polyline points="10 17 15 12 10 7"></polyline>
                            <line x1="15" y1="12" x2="3" y2="12"></line>
                        </svg>
                    </button>

                    <div class="forgot-password-container">
                        <button type="button" onclick="openForgotPasswordModal()" class="forgot-password-btn">
                            <svg class="nav-icon-svg" style="width: 14px; height: 14px; stroke: #2563eb;" viewBox="0 0 24 24">
                                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                            </svg>
                            <span>هل نسيت كلمة المرور؟</span>
                        </button>
                    </div>
                </form>

                <!-- First-Time Administrator Setup Form (Preserved) -->
                <form id="form-first-time-setup" style="display: none;" onsubmit="event.preventDefault(); submitFirstTimeSetup();">
                    <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 12.5px; color: #0369a1; line-height: 1.6;">
                        <strong>تهيئة المنظومة لأول مرة:</strong> يرجى إنشاء حساب مدير النظام الرئيسي وتعيين بيانات الدخول الخاصة به.
                    </div>
                    <div class="login-field-group">
                        <label class="login-field-label">الاسم الكامل لمدير المنظومة:</label>
                        <input type="text" id="setup-fullname" class="login-input-premium" placeholder="مثال: د. طارق عبد الرحمن" required>
                    </div>
                    <div class="login-field-group">
                        <label class="login-field-label">اسم المستخدم (Username):</label>
                        <input type="text" id="setup-username" class="login-input-premium" placeholder="مثال: admin" required>
                    </div>
                    <div class="login-field-group">
                        <label class="login-field-label">كلمة المرور الجديدة:</label>
                        <input type="password" id="setup-password" class="login-input-premium" placeholder="••••••••" required>
                    </div>
                    <button type="submit" id="btn-setup-submit" class="login-submit-btn-premium" style="background: #059669;">
                        <svg class="nav-icon-svg" style="width:18px; height:18px; stroke:white;" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"></path></svg>
                        <span>إنشاء حساب مدير المنظومة والبدء</span>
                    </button>
                </form>
            </div>

            <!-- Footer of Right Section -->
            <div class="login-footer-institutional">
                <div class="login-footer-copy">جميع الحقوق محفوظة © كلية الدراسات العليا — أكاديمية الشرطة</div>
                <div class="login-footer-sub">منظومة الفحص الأكاديمي الموحدة — الإصدار 2.4 (تشغيل محلي بالكامل)</div>
            </div>
        </div>

        <!-- Left / Hero Showcase Side (~69% width, Authentic Police Academy photo) -->
        <div class="login-hero-side">
            <div class="login-hero-overlay"></div>
            <div class="login-hero-content">
                <h1 class="login-hero-title">
                    <span class="hero-title-accent-bar"></span>
                    <span>نظام كشف الاستلال العلمي والاستشهادات</span>
                </h1>
                <p class="login-hero-desc">
                    منظومة فحص أكاديمي متكاملة لخدمة كلية الدراسات العليا بأكاديمية الشرطة، تساعد في مراجعة التطابق والاستنساخ وإعادة الصياغة، والتحليل التجريبي للكتابة بالذكاء الاصطناعي.
                </p>

                <!-- 3 Capability Highlights (Horizontal) -->
                <div class="hero-features-row">
                    <!-- Feature 1: Text Plagiarism -->
                    <div class="hero-feature-item">
                        <div class="hero-feature-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="11" cy="11" r="8"></circle>
                                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                            </svg>
                        </div>
                        <div class="hero-feature-text">
                            <div class="hero-feature-title">كشف الاستلال النصي</div>
                            <div class="hero-feature-sub">(التطابق الحرفي والجزئي)</div>
                        </div>
                    </div>

                    <!-- Divider -->
                    <div class="hero-feature-divider"></div>

                    <!-- Feature 2: Semantic Analysis -->
                    <div class="hero-feature-item">
                        <div class="hero-feature-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                                <polyline points="2 17 12 22 22 17"></polyline>
                                <polyline points="2 12 12 17 22 12"></polyline>
                            </svg>
                        </div>
                        <div class="hero-feature-text">
                            <div class="hero-feature-title">تحليل دلالي متقدم</div>
                            <div class="hero-feature-sub">(تشابه المعنى وإعادة الصياغة)</div>
                        </div>
                    </div>

                    <!-- Divider -->
                    <div class="hero-feature-divider"></div>

                    <!-- Feature 3: Experimental AI Analysis -->
                    <div class="hero-feature-item">
                        <div class="hero-feature-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                <polyline points="14 2 14 8 20 8"></polyline>
                                <line x1="16" y1="13" x2="8" y2="13"></line>
                                <line x1="16" y1="17" x2="8" y2="17"></line>
                                <path d="M10 9h2"></path>
                            </svg>
                        </div>
                        <div class="hero-feature-text">
                            <div class="hero-feature-title">تحليل تجريبي للذكاء الاصطناعي</div>
                            <div class="hero-feature-sub">(للمستخدمين المصرح لهم)</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
'''

# JavaScript addition for togglePasswordVisibility
js_func_to_add = '''        function togglePasswordVisibility() {
            const pwdInp = document.getElementById('login-password');
            const eyeOpen = document.getElementById('eye-icon-open');
            const eyeClosed = document.getElementById('eye-icon-closed');
            if (!pwdInp) return;
            if (pwdInp.type === 'password') {
                pwdInp.type = 'text';
                if (eyeOpen) eyeOpen.style.display = 'none';
                if (eyeClosed) eyeClosed.style.display = 'block';
            } else {
                pwdInp.type = 'password';
                if (eyeOpen) eyeOpen.style.display = 'block';
                if (eyeClosed) eyeClosed.style.display = 'none';
            }
        }
'''

content = INDEX_PATH.read_text(encoding='utf-8')

# 1. Update CSS
c_start_idx = content.find(css_start)
c_end_idx = content.find(css_end)
assert c_start_idx != -1 and c_end_idx != -1, "CSS region not found"
content = content[:c_start_idx] + new_css + "\n" + content[c_end_idx:]

# 2. Update HTML
h_start_idx = content.find(html_start)
h_end_idx = content.find(html_end)
assert h_start_idx != -1 and h_end_idx != -1, "HTML region not found"
content = content[:h_start_idx] + new_html + "\n" + content[h_end_idx:]

# 3. Add togglePasswordVisibility if not present
if "function togglePasswordVisibility" not in content:
    submit_login_idx = content.find("async function submitLogin()")
    assert submit_login_idx != -1, "submitLogin function not found"
    content = content[:submit_login_idx] + js_func_to_add + "\n        " + content[submit_login_idx:]

# 4. In submitLogin, update the button reset HTML to match
old_btn_reset = "<span>تسجيل الدخول للنظام</span>"
new_btn_reset = "<span>تسجيل الدخول</span>"
# We can replace in the submitLogin function
content = content.replace(
    'submitBtn.innerHTML = \'<svg class="nav-icon-svg" style="width:16px; height:16px; stroke:white;" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line></svg><span>تسجيل الدخول للنظام</span>\';',
    'submitBtn.innerHTML = \'<span>تسجيل الدخول</span><svg class="nav-icon-svg" style="width:18px; height:18px; stroke:white;" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line></svg>\';'
)

INDEX_PATH.write_text(content, encoding='utf-8')
print("Successfully applied login redesign to templates/index.html")

# Also copy to any unpacked temp directories
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

print(f"Updated template in {updated_meis} unpacked temp directories!")
