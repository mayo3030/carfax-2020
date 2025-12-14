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

# ملف الـ Tokens
TOKENS_FILE = Path(os.getenv("TOKENS_FILE", DATA_DIR / "tokens.json"))

# إعدادات المتصفح
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# استخدام Chrome Profile (لتجاوز الـ CAPTCHA)
USE_CHROME_PROFILE = os.getenv("USE_CHROME_PROFILE", "false").lower() == "true"
# مسار Chrome User Data (عادة في AppData\Local\Google\Chrome\User Data)
CHROME_USER_DATA_DIR = os.getenv(
    "CHROME_USER_DATA_DIR", 
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
)
# اسم الـ Profile (Default أو Profile 1, Profile 2, etc)
CHROME_PROFILE = os.getenv("CHROME_PROFILE", "Default")

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

# === Bright Data Proxy ===
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "false").lower() == "true"
PROXY_SERVER = os.getenv("PROXY_SERVER", "brd.superproxy.io:33335")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")
PROXY_COUNTRY = os.getenv("PROXY_COUNTRY", "us")


def validate_credentials() -> bool:
    """التحقق من وجود بيانات الاعتماد"""
    return bool(CARFAX_EMAIL and CARFAX_PASSWORD)


def get_playwright_proxy() -> dict | None:
    """
    الحصول على إعدادات البروكسي لـ Playwright
    
    Returns:
        قاموس إعدادات البروكسي أو None إذا كان معطل
    """
    if not PROXY_ENABLED or not PROXY_USERNAME:
        return None
    
    # بناء اسم المستخدم مع الدولة
    username = PROXY_USERNAME
    if PROXY_COUNTRY:
        username += f"-country-{PROXY_COUNTRY}"
    
    return {
        "server": f"http://{PROXY_SERVER}",
        "username": username,
        "password": PROXY_PASSWORD
    }


def get_httpx_proxy() -> str | None:
    """
    الحصول على رابط البروكسي لـ httpx
    
    Returns:
        رابط البروكسي أو None إذا كان معطل
    """
    if not PROXY_ENABLED or not PROXY_USERNAME:
        return None
    
    # بناء اسم المستخدم مع الدولة
    username = PROXY_USERNAME
    if PROXY_COUNTRY:
        username += f"-country-{PROXY_COUNTRY}"
    
    return f"http://{username}:{PROXY_PASSWORD}@{PROXY_SERVER}"


def get_config_summary() -> dict:
    """إرجاع ملخص الإعدادات (بدون بيانات حساسة)"""
    return {
        "base_dir": str(BASE_DIR),
        "output_dir": str(OUTPUT_DIR),
        "cookies_file": str(COOKIES_FILE),
        "headless": HEADLESS,
        "has_credentials": validate_credentials(),
        "delay_range": f"{MIN_DELAY}-{MAX_DELAY}s",
        "proxy_enabled": PROXY_ENABLED,
        "proxy_server": PROXY_SERVER if PROXY_ENABLED else "غير مفعل"
    }

