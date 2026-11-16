# -*- coding: utf-8 -*-
"""
Launches Flask app locally on port 5055, logs in, navigates to upload view,
simulates the mockup files, and captures screenshots with Google Chrome via Playwright.
"""
import os
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

os.environ['TESTING'] = '0'

from app import create_app

app = create_app()

def run_server():
    app.run(host='127.0.0.1', port=5055, debug=False, use_reloader=False)

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    output_dir = Path('docs/ui_screenshots')
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chrome_path)
        
        # 1. Desktop 1920x1080 Viewport
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.goto('http://127.0.0.1:5055/')
        page.wait_for_selector('#login-username', timeout=10000)

        # Login
        page.fill('#login-username', 'Tamer Darwish')
        page.fill('#login-password', 'Academic@2026#Secure')
        page.click('button[type="submit"]')
        page.wait_for_selector('#user-profile-badge', timeout=10000)
        time.sleep(1)

        # Switch to upload view
        page.click('#nav-upload')
        time.sleep(1)

        # Screenshot 1: Empty state
        page.screenshot(path=str(output_dir / 'upload_view_empty_1920.png'), full_page=False)
        print('Saved upload_view_empty_1920.png')

        # Simulate 2 files matching the mockup
        page.evaluate('''() => {
            const file1 = new File(["dummy content 1"], "الفصل الأول - الإطار النظري.pdf", { type: "application/pdf" });
            Object.defineProperty(file1, 'size', { value: 2.41 * 1024 * 1024 });
            const file2 = new File(["dummy content 2"], "الفصل الثاني - الدراسات السابقة.pdf", { type: "application/pdf" });
            Object.defineProperty(file2, 'size', { value: 1.87 * 1024 * 1024 });
            handleFileList([file1, file2]);
        }''')
        time.sleep(1)

        # Screenshot 2: Mockup matched state at 1920x1080
        page.screenshot(path=str(output_dir / 'upload_view_with_files_1920.png'), full_page=False)
        print('Saved upload_view_with_files_1920.png')

        # 2. Laptop 1366x768 Viewport (resize existing logged-in page)
        page.set_viewport_size({'width': 1366, 'height': 768})
        time.sleep(1)
        page.screenshot(path=str(output_dir / 'upload_view_with_files_1366.png'), full_page=False)
        print('Saved upload_view_with_files_1366.png')

        browser.close()
        print('All screenshots captured successfully.')
        os._exit(0)

if __name__ == '__main__':
    main()
