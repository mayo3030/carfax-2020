"""
Configuration Module
====================
إدارة الإعدادات والمتغيرات البيئية
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

# المسارات الأساسية
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", DATA_DIR / "output"))

# التأكد من وجود المجلدات
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# بيانات الاعتماد
CARFAX_EMAIL = os.getenv("CARFAX_EMAIL", "")
CARFAX_PASSWORD = os.getenv("CARFAX_PASSWORD", "")

# ملف الـ Cookies
COOKIES_FILE = Path(os.getenv("COOKIES_FILE", DATA_DIR / "cookies.txt"))

# إعدادات المتصفح
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# تأخير بين الطلبات
MIN_DELAY = float(os.getenv("MIN_DELAY", "2"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "5"))

# URLs
CARFAX_BASE_URL = "https://www.carfaxonline.com"
CARFAX_LOGIN_URL = "https://www.carfaxonline.com/login"
AUTH0_LOGIN_URL = "https://auth.carfax.com/u/login"

# User Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def validate_credentials() -> bool:
    """التحقق من وجود بيانات الاعتماد"""
    return bool(CARFAX_EMAIL and CARFAX_PASSWORD)


def get_config_summary() -> dict:
    """إرجاع ملخص الإعدادات (بدون بيانات حساسة)"""
    return {
        "base_dir": str(BASE_DIR),
        "output_dir": str(OUTPUT_DIR),
        "cookies_file": str(COOKIES_FILE),
        "headless": HEADLESS,
        "has_credentials": validate_credentials(),
        "delay_range": f"{MIN_DELAY}-{MAX_DELAY}s"
    }

