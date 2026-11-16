# -*- coding: utf-8 -*-
"""
Launches Flask app locally on port 5059, logs in as Dr. Tamer Darwish,
verifies the enhanced Home Dashboard, and captures screenshots at:
- 1920x1080
- 1366x768
- 1152x650
Also builds a side-by-side comparison with the approved reference image.
"""
import os
import sys
import time
import shutil
import threading
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

os.environ['TESTING'] = '0'

from app import create_app

app = create_app()

def run_server():
    app.run(host='127.0.0.1', port=5059, debug=False, use_reloader=False)

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    output_dir = Path('docs/ui_screenshots')
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(r'C:\Users\user\.gemini\antigravity\brain\125d68d3-f36c-46e2-85c0-e920ab5c6000')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chrome_path)

        viewports = [
            ('dashboard_1920.png', 1920, 1080),
            ('dashboard_1366.png', 1366, 768),
            ('dashboard_1152.png', 1152, 650)
        ]

        for filename, width, height in viewports:
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.goto('http://127.0.0.1:5059/')
            page.wait_for_selector('#login-username', timeout=10000)

            # Login
            page.fill('#login-username', 'Tamer Darwish')
            page.fill('#login-password', 'Academic@2026#Secure')
            page.click('button[type="submit"]')
            page.wait_for_selector('#user-profile-badge', timeout=10000)
            page.wait_for_selector('#view-dashboard', timeout=10000)
            
            # Ensure dashboard view is active and loaded
            page.evaluate("switchView('dashboard')")
            time.sleep(1.5)

            out_path = output_dir / filename
            page.screenshot(path=str(out_path), full_page=False)
            print(f"Captured {filename} ({width}x{height})")

            # Copy to artifact directory
            if artifact_dir.exists():
                shutil.copyfile(str(out_path), str(artifact_dir / filename))
                print(f"Copied {filename} to artifact directory.")

            page.close()

        browser.close()

    # Generate side-by-side comparison
    ref_path = Path(r"C:\Users\user\.gemini\antigravity\brain\125d68d3-f36c-46e2-85c0-e920ab5c6000\.user_uploaded\media_1794853811169_9e477511.jpg")
    actual_path = output_dir / 'dashboard_1920.png'

    if ref_path.exists() and actual_path.exists():
        ref_img = Image.open(ref_path).convert('RGB')
        act_img = Image.open(actual_path).convert('RGB')

        target_h = 700
        # Resize ref
        ref_w = int(ref_img.width * (target_h / ref_img.height))
        ref_resized = ref_img.resize((ref_w, target_h), Image.Resampling.LANCZOS)

        # Resize act
        act_w = int(act_img.width * (target_h / act_img.height))
        act_resized = act_img.resize((act_w, target_h), Image.Resampling.LANCZOS)

        # Combine
        combined_w = ref_w + act_w + 30
        combined = Image.new('RGB', (combined_w, target_h + 60), color=(15, 23, 42))

        # Paste side by side
        # Right: Reference mockup
        # Left: Actual system
        combined.paste(ref_resized, (act_w + 20, 45))
        combined.paste(act_resized, (10, 45))

        comp_path = output_dir / 'dashboard_side_by_side_comparison.png'
        combined.save(str(comp_path))
        print("Saved side-by-side comparison at", comp_path)

        if artifact_dir.exists():
            shutil.copyfile(str(comp_path), str(artifact_dir / 'dashboard_side_by_side_comparison.png'))
            print("Copied comparison to artifact directory.")

if __name__ == '__main__':
    main()
