"""
Cookie Manager Module
====================
إدارة تحميل وحفظ والتحقق من الـ cookies
"""

import time
from pathlib import Path
from typing import Optional
from http.cookiejar import MozillaCookieJar, Cookie
from datetime import datetime

from rich.console import Console

console = Console()


class CookieManager:
    """
    إدارة cookies الجلسة
    
    - تحميل cookies من ملف Netscape format
    - حفظ cookies جديدة بعد تسجيل الدخول
    - التحقق من صلاحية الجلسة
    """
    
    # Cookies المطلوبة للمصادقة
    AUTH_COOKIES = [
        "auth0.u0ERZlg3gng09tmcfxmz3YesyFWWmloM.is.authenticated",
        "_legacy_auth0.u0ERZlg3gng09tmcfxmz3YesyFWWmloM.is.authenticated"
    ]
    
    def __init__(self, cookies_file: Path):
        """
        تهيئة مدير الـ Cookies
        
        Args:
            cookies_file: مسار ملف الـ cookies
        """
        self.cookies_file = Path(cookies_file)
        self.cookie_jar = MozillaCookieJar()
        self._cookies_dict: dict = {}
        
    def load(self) -> bool:
        """
        تحميل الـ cookies من الملف
        
        Returns:
            True إذا تم التحميل بنجاح
        """
        if not self.cookies_file.exists():
            console.print("[yellow]⚠ ملف الـ cookies غير موجود[/yellow]")
            return False
            
        try:
            self.cookie_jar.load(
                str(self.cookies_file),
                ignore_discard=True,
                ignore_expires=True
            )
            
            # تحويل إلى قاموس للوصول السهل
            self._cookies_dict = {
                cookie.name: cookie.value 
                for cookie in self.cookie_jar
            }
            
            console.print(f"[green]✓ تم تحميل {len(self._cookies_dict)} cookie[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]✗ خطأ في تحميل الـ cookies: {e}[/red]")
            return False
    
    def save(self) -> bool:
        """
        حفظ الـ cookies إلى الملف
        
        Returns:
            True إذا تم الحفظ بنجاح
        """
        try:
            # التأكد من وجود المجلد
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            
            self.cookie_jar.save(
                str(self.cookies_file),
                ignore_discard=True,
                ignore_expires=True
            )
            
            console.print(f"[green]✓ تم حفظ الـ cookies[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]✗ خطأ في حفظ الـ cookies: {e}[/red]")
            return False
    
    def is_session_valid(self) -> bool:
        """
        التحقق من صلاحية الجلسة
        
        Returns:
            True إذا كانت الجلسة صالحة
        """
        if not self._cookies_dict:
            return False
            
        # التحقق من وجود cookies المصادقة
        for auth_cookie in self.AUTH_COOKIES:
            if auth_cookie in self._cookies_dict:
                value = self._cookies_dict[auth_cookie]
                if value.lower() == "true":
                    # التحقق من تاريخ الانتهاء
                    if self._check_expiry(auth_cookie):
                        console.print("[green]✓ الجلسة صالحة[/green]")
                        return True
        
        console.print("[yellow]⚠ الجلسة منتهية أو غير صالحة[/yellow]")
        return False
    
    def _check_expiry(self, cookie_name: str) -> bool:
        """
        التحقق من تاريخ انتهاء cookie معين
        
        Args:
            cookie_name: اسم الـ cookie
            
        Returns:
            True إذا لم تنتهِ صلاحيته
        """
        for cookie in self.cookie_jar:
            if cookie.name == cookie_name:
                if cookie.expires is None or cookie.expires == 0:
                    # Session cookie - صالح
                    return True
                    
                # التحقق من الوقت
                current_time = int(time.time())
                if cookie.expires > current_time:
                    expires_dt = datetime.fromtimestamp(cookie.expires)
                    console.print(f"[dim]  ⏱ ينتهي في: {expires_dt}[/dim]")
                    return True
                    
        return False
    
    def get_cookies_for_playwright(self) -> list[dict]:
        """
        تحويل الـ cookies لتنسيق Playwright
        
        Returns:
            قائمة cookies بتنسيق Playwright
        """
        playwright_cookies = []
        
        for cookie in self.cookie_jar:
            # تنظيف domain
            domain = cookie.domain
            if domain and not domain.startswith('.'):
                domain = '.' + domain
            
            playwright_cookie = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": domain,
                "path": cookie.path or "/",
                "secure": cookie.secure,
                "httpOnly": False,
            }
            
            # إضافة تاريخ الانتهاء إذا موجود
            if cookie.expires and cookie.expires > 0:
                playwright_cookie["expires"] = float(cookie.expires)
            
            # إضافة sameSite
            playwright_cookie["sameSite"] = "Lax"
                
            playwright_cookies.append(playwright_cookie)
        
        console.print(f"[dim]  تم تحويل {len(playwright_cookies)} cookie لـ Playwright[/dim]")
            
        return playwright_cookies
    
    def update_from_playwright(self, cookies: list[dict]) -> None:
        """
        تحديث الـ cookies من Playwright
        
        Args:
            cookies: قائمة cookies من Playwright
        """
        for cookie_data in cookies:
            cookie = Cookie(
                version=0,
                name=cookie_data.get("name", ""),
                value=cookie_data.get("value", ""),
                port=None,
                port_specified=False,
                domain=cookie_data.get("domain", ""),
                domain_specified=True,
                domain_initial_dot=cookie_data.get("domain", "").startswith("."),
                path=cookie_data.get("path", "/"),
                path_specified=True,
                secure=cookie_data.get("secure", False),
                expires=cookie_data.get("expires"),
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False
            )
            
            self.cookie_jar.set_cookie(cookie)
            
        # تحديث القاموس
        self._cookies_dict = {
            cookie.name: cookie.value 
            for cookie in self.cookie_jar
        }
        
        console.print(f"[green]✓ تم تحديث {len(cookies)} cookie[/green]")
    
    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        الحصول على قيمة cookie
        
        Args:
            name: اسم الـ cookie
            default: القيمة الافتراضية
            
        Returns:
            قيمة الـ cookie أو القيمة الافتراضية
        """
        return self._cookies_dict.get(name, default)
    
    def clear(self) -> None:
        """مسح جميع الـ cookies"""
        self.cookie_jar.clear()
        self._cookies_dict.clear()
        console.print("[yellow]⚠ تم مسح جميع الـ cookies[/yellow]")
    
    def __len__(self) -> int:
        """عدد الـ cookies"""
        return len(self._cookies_dict)
    
    def __contains__(self, name: str) -> bool:
        """التحقق من وجود cookie"""
        return name in self._cookies_dict

