# -*- coding: utf-8 -*-
"""
Tests and captures screenshots of the redesigned login page:
1. 1920x1080 Desktop Viewport
2. 1366x768 Laptop Viewport
3. Password Visibility Toggle
4. Login Failure Error State
5. Login Success Workflow
"""
import os
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['TESTING'] = '0'

from playwright.sync_api import sync_playwright
from app import create_app

app = create_app()

def run_server():
    app.run(host='127.0.0.1', port=5057, debug=False, use_reloader=False)

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    output_dir = ROOT / 'docs' / 'ui_screenshots'
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chrome_path)
        
        # 1. 1920x1080 Viewport
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.goto('http://127.0.0.1:5057/')
        page.wait_for_selector('#login-screen', timeout=8000)
        time.sleep(1)

        # Verify key DOM elements
        assert page.is_visible('.login-screen-wrapper')
        assert page.is_visible('.login-form-side')
        assert page.is_visible('.login-hero-side')
        assert page.is_visible('.login-brand-logo-center')
        assert page.is_visible('#login-title-heading')
        assert page.is_visible('.login-badge-pill')
        assert page.is_visible('#login-username')
        assert page.is_visible('#login-password')
        assert page.is_visible('#btn-toggle-password-visibility')
        assert page.is_visible('#btn-login-submit')
        assert page.is_visible('.forgot-password-btn')
        assert page.is_visible('.hero-features-row')

        print("1. All login DOM elements verified successfully.")

        # Capture Clean 1920x1080 Screenshot
        screenshot_1920 = output_dir / 'login_redesign_1920.png'
        page.screenshot(path=str(screenshot_1920), full_page=False)
        print(f"2. Saved: {screenshot_1920}")

        # 2. Test Password Visibility Toggle
        page.fill('#login-username', 'Tamer Darwish')
        page.fill('#login-password', 'Academic@2026#Secure')
        
        # Verify initial type is password
        pwd_type_initial = page.get_attribute('#login-password', 'type')
        assert pwd_type_initial == 'password'
        
        # Click toggle
        page.click('#btn-toggle-password-visibility')
        time.sleep(0.3)
        pwd_type_toggled = page.get_attribute('#login-password', 'type')
        assert pwd_type_toggled == 'text'
        print("3. Password visibility toggle works (password -> text).")
        
        # Capture password visible state
        page.screenshot(path=str(output_dir / 'login_password_visible.png'), full_page=False)

        # Toggle back to password
        page.click('#btn-toggle-password-visibility')
        time.sleep(0.3)
        pwd_type_back = page.get_attribute('#login-password', 'type')
        assert pwd_type_back == 'password'
        print("4. Password visibility toggled back (text -> password).")

        # 3. Test Login Failure / Error Handling
        page.fill('#login-username', 'wrong_officer')
        page.fill('#login-password', 'WrongPassword!123')
        page.click('#btn-login-submit')
        time.sleep(1)

        assert page.is_visible('#login-error-alert')
        err_msg = page.inner_text('#login-error-text').strip()
        print(f"5. Login failure error displayed clearly: '{err_msg}'")
        page.screenshot(path=str(output_dir / 'login_error_state.png'), full_page=False)

        # 4. 1366x768 Viewport
        page.set_viewport_size({'width': 1366, 'height': 768})
        page.reload()
        page.wait_for_selector('#login-screen', timeout=8000)
        time.sleep(1)
        screenshot_1366 = output_dir / 'login_redesign_1366.png'
        page.screenshot(path=str(screenshot_1366), full_page=False)
        print(f"6. Saved: {screenshot_1366}")

        # 5. Test Login Success
        page.fill('#login-username', 'Tamer Darwish')
        page.fill('#login-password', 'Academic@2026#Secure')
        page.click('#btn-login-submit')
        page.wait_for_selector('#user-profile-badge', timeout=10000)
        print("7. Login success verified: entered application shell successfully.")

        browser.close()
        print("\nALL LOGIN ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!")
        os._exit(0)

if __name__ == '__main__':
    main()
