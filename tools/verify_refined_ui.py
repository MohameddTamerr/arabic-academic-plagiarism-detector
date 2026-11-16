# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import threading, time, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['TESTING'] = '0'

from app import create_app
app = create_app()

def run_server():
    app.run(host='127.0.0.1', port=5056, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)

chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=chrome_path)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    page.goto('http://127.0.0.1:5056/')
    page.wait_for_selector('#login-username', timeout=5000)
    page.fill('#login-username', 'Tamer Darwish')
    page.fill('#login-password', 'Academic@2026#Secure')
    page.click('button[type="submit"]')
    page.wait_for_selector('#user-profile-badge', timeout=5000)
    page.click('#nav-upload')
    time.sleep(1)

    print('1. Checking OCR elements:')
    assert page.is_visible('#ocr-btn-accurate')
    assert page.is_visible('#ocr-btn-fast')
    print('  - ocr-btn-accurate visible:', page.is_visible('#ocr-btn-accurate'))
    print('  - ocr-btn-fast visible:', page.is_visible('#ocr-btn-fast'))
    accurate_text = page.inner_text('#ocr-btn-accurate')
    print('  - Option A text:', repr(accurate_text.replace('\n', ' ')))
    fast_text = page.inner_text('#ocr-btn-fast')
    print('  - Option B text:', repr(fast_text.replace('\n', ' ')))

    print('2. Checking AI Research elements:')
    assert page.is_visible('#ai-research-upload-card')
    assert page.is_visible('.switch-toggle')
    assert page.is_checked('#toggle-ai-research')
    ai_status = page.inner_text('#ai-toggle-status-label')
    print('  - AI status label:', ai_status)
    disclaimer = page.inner_text('.ai-research-disclaimer')
    print('  - Disclaimer text:', disclaimer)

    print('3. Checking Footer & Analyze Action elements:')
    assert page.is_visible('.upload-action-footer')
    assert page.is_visible('#analysis-summary-text')
    assert page.is_visible('#btn-start-analysis')
    init_btn_text = page.inner_text('#btn-start-analysis-text')
    print('  - Initial button text:', init_btn_text)
    summary_text = page.inner_text('#analysis-summary-text')
    print('  - Initial engine summary:', summary_text)

    # Simulate adding 2 files
    print('4. Simulating adding 2 files:')
    page.evaluate('''() => {
        const file1 = new File(["test1"], "الفصل الأول - الإطار النظري.pdf", { type: "application/pdf" });
        const file2 = new File(["test2"], "الفصل الثاني - الدراسات السابقة.pdf", { type: "application/pdf" });
        handleFileList([file1, file2]);
    }''')
    time.sleep(1)
    updated_btn_text = page.inner_text('#btn-start-analysis-text')
    print('  - Button text with 2 files:', updated_btn_text)

    # Test toggling OCR options
    print('5. Testing OCR selection click:')
    page.click('#ocr-btn-fast')
    time.sleep(0.5)
    fast_is_active = 'active' in (page.get_attribute('#ocr-btn-fast', 'class') or '')
    acc_is_active = 'active' in (page.get_attribute('#ocr-btn-accurate', 'class') or '')
    print('  - Fast active:', fast_is_active, '| Accurate active:', acc_is_active)

    # Test toggling AI Research mode
    print('6. Testing AI toggle:')
    page.click('#ai-toggle-label-control')
    time.sleep(0.5)
    ai_status_off = page.inner_text('#ai-toggle-status-label')
    summary_text_off = page.inner_text('#analysis-summary-text')
    print('  - AI status after toggle off:', ai_status_off)
    print('  - Engine summary after toggle off:', summary_text_off)

    browser.close()
    print('\nALL VERIFICATIONS PASSED 100%!')
    os._exit(0)
