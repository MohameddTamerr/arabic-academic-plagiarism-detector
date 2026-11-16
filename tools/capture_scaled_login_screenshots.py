# -*- coding: utf-8 -*-
"""
Captures screenshots of the scaled login page across all required viewports:
- 1920x1080
- 1366x768
- 1280x720
- 1152x650
And generates a direct side-by-side comparison with the approved reference mockup.
"""
import os
import sys
import time
import threading
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['TESTING'] = '0'

from playwright.sync_api import sync_playwright
from app import create_app

app = create_app()

def run_server():
    app.run(host='127.0.0.1', port=5058, debug=False, use_reloader=False)

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    output_dir = ROOT / 'docs' / 'ui_screenshots'
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chrome_path)
        
        resolutions = [
            (1920, 1080, 'login_scaled_1920.png'),
            (1366, 768, 'login_scaled_1366.png'),
            (1280, 720, 'login_scaled_1280.png'),
            (1152, 650, 'login_scaled_1152.png'),
        ]

        for width, height, filename in resolutions:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.goto('http://127.0.0.1:5058/')
            page.wait_for_selector('#login-screen', timeout=8000)
            time.sleep(0.8)
            filepath = output_dir / filename
            page.screenshot(path=str(filepath), full_page=False)
            print(f"Captured {width}x{height} -> {filepath}")
            page.close()

        browser.close()

    # Generate visual side-by-side comparison with approved reference
    ref_path = Path(r'C:\Users\user\.gemini\antigravity\brain\125d68d3-f36c-46e2-85c0-e920ab5c6000\.user_uploaded\media_1794851382267_00de885b.jpg')
    if ref_path.exists():
        ref_img = Image.open(ref_path)
        actual_1920 = Image.open(output_dir / 'login_scaled_1920.png')

        # Resize actual 1920 image to reference height for 1:1 proportion inspection
        h = ref_img.height
        w = int(actual_1920.width * (h / actual_1920.height))
        actual_resized = actual_1920.resize((w, h), Image.Resampling.LANCZOS)

        comparison = Image.new('RGB', (ref_img.width + w + 10, h), (240, 240, 240))
        comparison.paste(ref_img, (0, 0))
        comparison.paste(actual_resized, (ref_img.width + 10, 0))
        comp_path = output_dir / 'login_scaled_comparison.png'
        comparison.save(comp_path)
        print(f"Comparison saved -> {comp_path}")

    print("All captures completed successfully!")
    os._exit(0)

if __name__ == '__main__':
    main()
