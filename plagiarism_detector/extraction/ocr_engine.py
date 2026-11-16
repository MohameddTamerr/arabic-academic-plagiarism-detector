# -*- coding: utf-8 -*-
"""
محرك التعرف الضوئي على الحروف المشروط (Conditional Offline OCR Engine):
- يعمل أوفلاين بالكامل باستخدام محرك Tesseract-OCR المحلي المثبت مسبقاً.
- يُستدعى فقط في حال كانت صفحة الـ PDF مصمتة أو مسحوبة عبر الماسح الضوئي (Scanner).
- لا يُنزل أي نماذج عبر الإنترنت، ويوفر فحصاً آمناً للجاهزية دون التسبب في انهيار النظام.
"""

import os
import time
import json
import uuid
import shutil
import hashlib
import logging
import threading
from functools import lru_cache
from pathlib import Path
from datetime import datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)

# حماية داخلية لتنفيذ Tesseract على مستوى خيوط العملية الواحدة (Intra-Process Thread Semaphore)
_OCR_SEMAPHORE = threading.Semaphore(getattr(config, 'MAX_CONCURRENT_OCR_JOBS', 1))


def get_ocr_semaphore() -> threading.Semaphore:
    """الحصول على السيمافور الداخلي الحاكم لعمليات OCR على مستوى العملية."""
    return _OCR_SEMAPHORE


def get_ocr_lock_path() -> Path:
    """استرجاع والتأكد من مسار ملف قفل OCR الحاكم عبر العمليات."""
    custom_path = getattr(config, 'OCR_LOCK_FILE', None)
    if custom_path:
        p = Path(custom_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    s_root = getattr(config, 'STORAGE_ROOT', None)
    if not s_root:
        s_root = Path(getattr(config, 'TEMP_UPLOAD_DIR', None) or '.')
    s_root.mkdir(parents=True, exist_ok=True)
    return s_root / '.ocr.lock'


class CrossProcessOcrLock:
    """
    قفل تنفيذ OCR الحاكم عبر العمليات المتعددة (Cross-Process Authoritative OCR Execution Slot):
    - يضمن عدم تجاوز عدد فتحات Tesseract المضبوط عبر كافة عمليات نظام التشغيل.
    - يعتمد على ملف قفل ذري (.ocr.lock) مدعوم برقم العملية (PID) وطابع زمني وهوية فريدة.
    - يدعم كشف واسترداد الأقفال الميتة (Stale Locks) إذا توقفت العملية السابقة دون تحرير القفل.
    - يضمن التحرير الحتمي للقفل في كتلة finally أو عند خروج مدير السياق.
    """
    def __init__(self, owner: str = 'system', timeout_seconds: int = 60, lock_file_path: Optional[Path] = None):
        self.owner = owner
        self.timeout_seconds = timeout_seconds
        base_lock_file = lock_file_path or get_ocr_lock_path()
        slot_count = 1 if lock_file_path else max(1, int(getattr(config, 'MAX_CONCURRENT_OCR_JOBS', 1)))
        self._lock_candidates = [base_lock_file]
        self._lock_candidates.extend(
            base_lock_file.with_name(f'{base_lock_file.name}.{slot_no}')
            for slot_no in range(2, slot_count + 1)
        )
        self.lock_file = base_lock_file
        self.token = str(uuid.uuid4())
        self._fd = None
        self._acquired = False

    def acquire(self, blocking: bool = True, timeout_seconds: Optional[float] = None, poll_interval: float = 0.05) -> bool:
        max_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        start_time = time.time()
        while True:
            for candidate in self._lock_candidates:
                self.lock_file = candidate
                if self.lock_file.exists() and not self._check_and_clean_stale_lock():
                    continue

                # محاولة إنشاء فتحة القفل ذرياً على مستوى نظام التشغيل.
                try:
                    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
                    self._fd = os.open(str(self.lock_file), flags, 0o600)
                    payload = {
                        'token': self.token,
                        'owner': self.owner,
                        'pid': os.getpid(),
                        'acquired_at': datetime.utcnow().isoformat(),
                        'expires_at': time.time() + self.timeout_seconds
                    }
                    os.write(self._fd, json.dumps(payload).encode('utf-8'))
                    self._acquired = True
                    return True
                except (FileExistsError, OSError):
                    continue

            if not blocking or time.time() - start_time > max_timeout:
                return False
            time.sleep(poll_interval)

    def _check_and_clean_stale_lock(self) -> bool:
        try:
            if not self.lock_file.exists():
                return True
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    self._force_remove_lock_file()
                    return True
                data = json.loads(content)

            expires_at = data.get('expires_at', 0)
            pid = data.get('pid')

            # العملية الحية تظل مالكة للفتحة حتى إن تجاوزت صفحة صعبة مدة
            # التأجير الاسمية؛ وإلا قد يبدأ Tesseract آخر فوقها ويستهلك الذاكرة.
            if pid and self._is_process_alive(pid):
                return False

            if pid and not self._is_process_alive(pid):
                logger.warning(f"تم اكتشاف قفل OCR لعملية غير موجودة (Dead PID {pid}). جاري الاسترداد...")
                self._force_remove_lock_file()
                return True

            if time.time() > expires_at:
                logger.warning(f"تم اكتشاف قفل OCR منتهي الصلاحية (Stale Lock) لمالكه {data.get('owner')} (PID {pid}). جاري الاسترداد...")
                self._force_remove_lock_file()
                return True

            return False
        except Exception as e:
            logger.warning(f"تعذر فحص ملف قفل OCR: {e}. جاري تجاوزه...")
            self._force_remove_lock_file()
            return True

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if process:
                    wait_res = kernel32.WaitForSingleObject(process, 0)
                    kernel32.CloseHandle(process)
                    # 0x00000102 (WAIT_TIMEOUT) means the process is still running (unsignaled)
                    return wait_res == 0x00000102
                return False
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def _force_remove_lock_file(self):
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None
            if self.lock_file.exists():
                os.unlink(str(self.lock_file))
        except Exception as e:
            logger.error(f"خطأ أثناء إزالة ملف قفل OCR القديم: {e}")

    def release(self):
        if not self._acquired:
            return
        try:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None

            if self.lock_file.exists():
                try:
                    with open(self.lock_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get('token') == self.token or data.get('pid') == os.getpid():
                        os.unlink(str(self.lock_file))
                except Exception:
                    if self.lock_file.exists():
                        os.unlink(str(self.lock_file))
        finally:
            self._acquired = False

    def __enter__(self):
        if not self.acquire(blocking=True):
            raise RuntimeError("تعذر حجز فتحة تشغيل OCR عبر العمليات ضمن المهلة المحددة (Cross-Process OCR Slot Busy).")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# مسارات تيسيراكت الافتراضية على أنظمة ويندوز
_COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
]


OCR_MODE_ACCURATE = 'accurate'
OCR_MODE_FAST = 'fast'
OCR_MODES = frozenset((OCR_MODE_ACCURATE, OCR_MODE_FAST))


def normalize_ocr_mode(ocr_mode: str | None) -> str:
    """Return a supported OCR mode, defaulting safely to the accurate model."""
    normalized = str(ocr_mode or OCR_MODE_ACCURATE).strip().lower()
    return normalized if normalized in OCR_MODES else OCR_MODE_ACCURATE


def find_tessdata_dir(ocr_mode: str = OCR_MODE_ACCURATE) -> Path | None:
    """Locate the selected bundled Arabic/English OCR models."""
    mode = normalize_ocr_mode(ocr_mode)
    directory_name = 'tessdata_fast' if mode == OCR_MODE_FAST else 'tessdata'
    candidates = [
        Path(getattr(config, 'BUNDLE_DIR', config.BASE_DIR)) / directory_name,
        Path(config.BASE_DIR) / 'assets' / directory_name,
    ]
    for candidate in candidates:
        if (candidate / 'ara.traineddata').is_file() and (candidate / 'eng.traineddata').is_file():
            return candidate.resolve()
    return None


def find_tesseract_cmd() -> str | None:
    """البحث التلقائي عن مسار tesseract.exe على نظام ويندوز."""
    # 1. فحص المتغير البيئي PATH
    cmd = shutil.which('tesseract')
    if cmd and os.path.exists(cmd):
        return cmd

    # 2. فحص المسارات القياسية المعروفة
    for p in _COMMON_TESSERACT_PATHS:
        if os.path.exists(p):
            return p

    return None


@lru_cache(maxsize=2)
def check_ocr_availability(ocr_mode: str = OCR_MODE_ACCURATE) -> dict:
    """
    التحقق من جاهزية محرك OCR المحلي وحزم اللغة العربية.
    """
    mode = normalize_ocr_mode(ocr_mode)
    cmd = find_tesseract_cmd()
    if not cmd:
        return {
            'available': False,
            'reason': 'برنامج Tesseract-OCR غير مثبت في المسار الافتراضي (C:\\Program Files\\Tesseract-OCR).',
            'has_arabic': False
        }

    tessdata_dir = find_tessdata_dir(mode)
    if not tessdata_dir:
        return {
            'available': True,
            'cmd_path': cmd,
            'has_arabic': False,
            'languages': [],
            'reason': 'محرك Tesseract متاح لكن حزمة OCR العربية المضمنة غير موجودة.'
        }

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        tessdata_arg = str(tessdata_dir)
        # pytesseract's --list-langs wrapper mis-parses custom tessdata paths on
        # some Windows builds. The packaged model files are authoritative here;
        # the engine itself is exercised separately by get_tesseract_version.
        pytesseract.get_tesseract_version()
        langs = sorted(path.stem for path in tessdata_dir.glob('*.traineddata'))
        has_arabic = ('ara' in langs) or ('Arabic' in langs)
        return {
            'available': True,
            'cmd_path': cmd,
            'has_arabic': has_arabic,
            'languages': langs,
            'tessdata_path': tessdata_arg,
            'ocr_mode': mode,
            'reason': 'محرك Tesseract جاهز ومتاح أوفلاين.' if has_arabic else 'Tesseract متاح لكن ينقصه ملف اللغة العربية (ara.traineddata).'
        }
    except Exception as e:
        return {
            'available': False,
            'reason': f'تعذر تشغيل pytesseract: {str(e)}',
            'has_arabic': False
        }


def _ocr_cache_path(
    image_bytes: bytes,
    languages: str,
    image_identity: str = '',
    ocr_mode: str = OCR_MODE_ACCURATE,
) -> Path | None:
    if not getattr(config, 'OCR_CACHE_ENABLED', True):
        return None
    cache_root = Path(getattr(config, 'OCR_CACHE_DIR', Path(config.STORAGE_ROOT) / 'ocr_cache'))
    cache_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    digest.update(b'ocr-cache-v2\0')
    digest.update(normalize_ocr_mode(ocr_mode).encode('ascii'))
    digest.update(b'\0')
    digest.update(languages.encode('utf-8'))
    digest.update(b'\0--oem=1--psm=3\0')
    digest.update(image_identity.encode('utf-8'))
    digest.update(b'\0')
    digest.update(image_bytes)
    return cache_root / f'{digest.hexdigest()}.json'


def _read_ocr_cache(cache_path: Path | None) -> str | None:
    if cache_path is None or not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
        text = payload.get('text')
        return text if isinstance(text, str) else None
    except Exception as exc:
        logger.debug("تعذر قراءة كاش OCR %s: %s", cache_path, exc)
        return None


def _write_ocr_cache(cache_path: Path | None, text: str) -> None:
    if cache_path is None or not text.strip():
        return
    temp_path = cache_path.with_name(f'.{cache_path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp_path.write_text(
            json.dumps({'text': text}, ensure_ascii=False),
            encoding='utf-8',
        )
        os.replace(temp_path, cache_path)
    except Exception as exc:
        logger.debug("تعذر حفظ كاش OCR %s: %s", cache_path, exc)
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


def ocr_page_pixmap(
    pixmap_or_image,
    languages: str = 'ara+eng',
    ocr_mode: str = OCR_MODE_ACCURATE,
) -> str:
    """
    تنفيذ OCR على صورة صفحة واحدة فقط، مع معالجة الأخطاء بأمان.
    """
    mode = normalize_ocr_mode(ocr_mode)
    status = (
        check_ocr_availability(mode)
        if mode == OCR_MODE_FAST
        else check_ocr_availability()
    )
    if not status['available'] or not status.get('has_arabic', False):
        logger.debug(f"تخطي OCR: {status['reason']}")
        return ''

    try:
        import pytesseract
        from PIL import Image, ImageOps
        import io

        pytesseract.pytesseract.tesseract_cmd = status['cmd_path']

        # إذا كان المدخل صورة PIL مباشرة أو fitz Pixmap
        if isinstance(pixmap_or_image, Image.Image):
            image = pixmap_or_image
            image_bytes = image.tobytes()
            image_identity = f'{image.mode}:{image.width}x{image.height}'
        elif hasattr(pixmap_or_image, 'tobytes'):
            img_bytes = pixmap_or_image.tobytes('png')
            image = Image.open(io.BytesIO(img_bytes))
            image_bytes = img_bytes
            image_identity = 'png'
        else:
            return ''

        # Grayscale improves old, textured Arabic periodicals while keeping the
        # operation light enough for very large PDFs.
        image = ImageOps.grayscale(image)
        cache_path = _ocr_cache_path(image_bytes, languages, image_identity, mode)
        cached_text = _read_ocr_cache(cache_path)
        if cached_text is not None:
            logger.debug("تم استخدام نتيجة OCR محفوظة لصفحة متطابقة.")
            return cached_text

        with _OCR_SEMAPHORE:
            timeout = getattr(config, 'OCR_LOCK_TIMEOUT_SECONDS', 60)
            ocr_lock = CrossProcessOcrLock(owner=f"ocr_proc_{os.getpid()}", timeout_seconds=timeout)
            if not ocr_lock.acquire(blocking=True, timeout_seconds=timeout):
                logger.warning("تعذر حجز فتحة تشغيل OCR عبر العمليات ضمن المهلة المحددة (Cross-Process OCR Slot Timeout).")
                return ''
            try:
                tessdata_path = status.get('tessdata_path')
                tessdata_config = f'--tessdata-dir {tessdata_path} ' if tessdata_path else ''
                text = pytesseract.image_to_string(
                    image,
                    lang=languages,
                    config=f'{tessdata_config}--oem 1 --psm 3'
                )
                result = text.strip()
                _write_ocr_cache(cache_path, result)
                return result
            finally:
                ocr_lock.release()
    except Exception as e:
        logger.warning(f"فشل أثناء إجراء OCR للصفحة: {e}")
        return ''


def ocr_page_pixmap_with_words(pixmap_or_image, languages: str = 'ara+eng',
                               ocr_mode: str = OCR_MODE_ACCURATE) -> dict:
    """Run local TSV OCR and retain only trustworthy word-level provenance.

    This is additive and intentionally not wired into report highlighting yet:
    callers must validate image-to-page geometry before using a rectangle.
    """
    mode = normalize_ocr_mode(ocr_mode)
    status = check_ocr_availability(mode) if mode == OCR_MODE_FAST else check_ocr_availability()
    empty = {'text': '', 'words': [], 'image_width': 0, 'image_height': 0,
             'provenance': 'ocr_unavailable', 'ocr_mode': mode}
    if not status.get('available') or not status.get('has_arabic'):
        return empty
    try:
        import io
        import pytesseract
        from PIL import Image, ImageOps
        from .ocr_coordinates import OcrWordBox
        pytesseract.pytesseract.tesseract_cmd = status['cmd_path']
        if isinstance(pixmap_or_image, Image.Image): image = pixmap_or_image
        elif hasattr(pixmap_or_image, 'tobytes'): image = Image.open(io.BytesIO(pixmap_or_image.tobytes('png')))
        else: return empty
        image = ImageOps.grayscale(image)
        cfg = f"--tessdata-dir {status.get('tessdata_path')} " if status.get('tessdata_path') else ''
        with _OCR_SEMAPHORE:
            with CrossProcessOcrLock(owner=f"ocr_tsv_{os.getpid()}", timeout_seconds=getattr(config, 'OCR_LOCK_TIMEOUT_SECONDS', 60)) as lock:
                data = pytesseract.image_to_data(image, lang=languages, config=f'{cfg}--oem 1 --psm 3', output_type=pytesseract.Output.DICT)
        words=[]; pieces=[]; offset=0
        for i, raw in enumerate(data.get('text', [])):
            text = (raw or '').strip()
            try: confidence=float(data['conf'][i])
            except (ValueError, TypeError, KeyError): confidence=-1.0
            if not text: continue
            if pieces: offset += 1
            start=offset; pieces.append(text); offset += len(text)
            words.append(OcrWordBox(text, confidence, int(data['left'][i]), int(data['top'][i]), int(data['width'][i]), int(data['height'][i]), start, offset))
        return {'text': ' '.join(pieces), 'words': words, 'image_width': image.width, 'image_height': image.height,
                'provenance': 'tesseract_tsv', 'ocr_mode': mode}
    except Exception as exc:
        logger.warning("فشل OCR TSV للصفحة: %s", exc)
        return empty
