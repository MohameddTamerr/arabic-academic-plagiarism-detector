from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import shutil

ref_path = Path(r"C:\Users\user\.gemini\antigravity\brain\125d68d3-f36c-46e2-85c0-e920ab5c6000\.user_uploaded\media_1794853811169_9e477511.jpg")
act_path = Path('docs/ui_screenshots/dashboard_1920.png')
artifact_dir = Path(r'C:\Users\user\.gemini\antigravity\brain\125d68d3-f36c-46e2-85c0-e920ab5c6000')

ref_img = Image.open(ref_path).convert('RGB')
act_img = Image.open(act_path).convert('RGB')

target_h = 750
ref_w = int(ref_img.width * (target_h / ref_img.height))
ref_resized = ref_img.resize((ref_w, target_h), Image.Resampling.LANCZOS)

act_w = int(act_img.width * (target_h / act_img.height))
act_resized = act_img.resize((act_w, target_h), Image.Resampling.LANCZOS)

header_h = 60
margin = 20
total_w = ref_w + act_w + margin * 3
total_h = target_h + header_h + margin * 2

canvas = Image.new('RGB', (total_w, total_h), color=(15, 23, 42)) # Slate 900
draw = ImageDraw.Draw(canvas)

try:
    font = ImageFont.truetype("arial.ttf", 22)
    font_sub = ImageFont.truetype("arial.ttf", 14)
except Exception:
    font = font_sub = ImageFont.load_default()

# Left panel: Actual System
canvas.paste(act_resized, (margin, header_h + margin))
draw.text((margin + 10, margin), "Actual Implemented System (1920x1080 Viewport)", fill=(56, 189, 248), font=font)
draw.text((margin + 10, margin + 28), "Live browser output - 100% dynamic data, zero mocked values", fill=(148, 163, 184), font=font_sub)

# Right panel: Approved Reference Mockup
ref_x = margin * 2 + act_w
canvas.paste(ref_resized, (ref_x, header_h + margin))
draw.text((ref_x + 10, margin), "Approved Reference Mockup (Source of Truth)", fill=(74, 222, 128), font=font)
draw.text((ref_x + 10, margin + 28), "Target visual reference provided by User", fill=(148, 163, 184), font=font_sub)

out_comp = Path('docs/ui_screenshots/dashboard_side_by_side_comparison.png')
canvas.save(str(out_comp))
print("Updated comparison image with labels.")

if artifact_dir.exists():
    shutil.copyfile(str(out_comp), str(artifact_dir / 'dashboard_side_by_side_comparison.png'))
    print("Copied to artifact directory.")
