"""
Auto Login Module
=================
تسجيل الدخول التلقائي باستخدام Playwright
"""

import asyncio
import random
from typing import Optional
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser
from rich.console import Console

from .cookies import CookieManager
from ..config import (
    CARFAX_EMAIL,
    CARFAX_PASSWORD,
    CARFAX_LOGIN_URL,
    CARFAX_BASE_URL,
    HEADLESS,
    MIN_DELAY,
    MAX_DELAY,
    USER_AGENT,
    PROXY_ENABLED,
    USE_CHROME_PROFILE,
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE,
    validate_credentials,
    get_playwright_proxy
)

console = Console()


class AutoLogin:
    """
    تسجيل الدخول التلقائي إلى Carfax
    
    يستخدم Playwright للتسجيل عند الحاجة
    ويحفظ الـ cookies للجلسات المستقبلية
    """
    
    # CSS Selectors لصفحة تسجيل الدخول
    SELECTORS = {
        "email_input": 'input[name="username"], input[type="email"], #username',
        "password_input": 'input[name="password"], input[type="password"], #password',
        "submit_button": 'button[type="submit"], button[name="action"], .auth0-lock-submit',
        "error_message": '.auth0-global-message-error, .error-message, [class*="error"]',
        "logged_in_indicator": '[class*="dealer"], [class*="logged-in"], .user-menu'
    }
    
    def __init__(self, cookie_manager: CookieManager):
        """
        تهيئة مسجل الدخول
        
        Args:
            cookie_manager: مدير الـ cookies
        """
        self.cookie_manager = cookie_manager
        
    async def login(self) -> bool:
        """
        تنفيذ تسجيل الدخول
        
        Returns:
            True إذا نجح تسجيل الدخول
        """
        if not validate_credentials():
            console.print("[red]✗ بيانات الاعتماد غير موجودة في .env[/red]")
            console.print("[dim]  أضف CARFAX_EMAIL و CARFAX_PASSWORD إلى ملف .env[/dim]")
            return False
            
        console.print("[blue]🔐 بدء تسجيل الدخول...[/blue]")
        
        # عرض حالة المتصفح
        if USE_CHROME_PROFILE:
            console.print("[cyan]  🌐 استخدام Chrome Profile الحالي[/cyan]")
        elif PROXY_ENABLED:
            console.print("[cyan]  🌐 البروكسي مفعل (Bright Data)[/cyan]")
        
        try:
            async with async_playwright() as p:
                # استخدام Chrome Profile إذا كان مفعل
                if USE_CHROME_PROFILE:
                    import os
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=os.path.join(CHROME_USER_DATA_DIR, CHROME_PROFILE),
                        channel="chrome",
                        headless=False,
                        viewport={"width": 1920, "height": 1080},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox"
                        ]
                    )
                    browser = None
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    # الوضع العادي
                    browser = await p.chromium.launch(
                        headless=HEADLESS,
                        proxy=get_playwright_proxy()
                    )
                    context = await browser.new_context(
                        user_agent=USER_AGENT,
                        viewport={"width": 1920, "height": 1080},
                        ignore_https_errors=PROXY_ENABLED
                    )
                    
                    # تحميل الـ cookies إذا موجودة
                    cookies = self.cookie_manager.get_cookies_for_playwright()
                    if cookies:
                        await context.add_cookies(cookies)
                    
                    page = await context.new_page()
                
                # الخطوة 1: فتح صفحة تسجيل الدخول
                console.print("[dim]  → فتح صفحة تسجيل الدخول...[/dim]")
                await page.goto(CARFAX_LOGIN_URL, wait_until="networkidle")
                
                # انتظار تحميل الصفحة
                await asyncio.sleep(2)
                
                # الخطوة 2: ملء البيانات والتسجيل
                console.print("[dim]  → إدخال بيانات الاعتماد...[/dim]")
                
                # تأخير عشوائي لمحاكاة السلوك البشري
                await asyncio.sleep(random.uniform(1, 2))
                
                # دالة مساعدة لإغلاق المتصفح
                async def close_browser():
                    if USE_CHROME_PROFILE:
                        await context.close()
                    else:
                        await browser.close()
                
                # ملء حقل البريد الإلكتروني
                email_filled = await self._fill_email(page)
                if not email_filled:
                    console.print("[red]✗ لم يتم العثور على حقل البريد الإلكتروني[/red]")
                    await close_browser()
                    return False
                
                await asyncio.sleep(random.uniform(0.5, 1))
                
                # ملء حقل كلمة المرور
                password_filled = await self._fill_password(page)
                if not password_filled:
                    console.print("[red]✗ لم يتم العثور على حقل كلمة المرور[/red]")
                    await close_browser()
                    return False
                
                await asyncio.sleep(random.uniform(0.5, 1))
                
                # النقر على زر تسجيل الدخول
                await self._click_submit(page)
                
                # انتظار التوجيه
                console.print("[dim]  → انتظار تسجيل الدخول...[/dim]")
                await asyncio.sleep(5)
                
                # الخطوة 3: التحقق من نجاح التسجيل
                if await self._verify_login(page):
                    console.print("[green]✓ تم تسجيل الدخول بنجاح![/green]")
                    
                    # حفظ الـ cookies الجديدة
                    await self._save_session_cookies(context)
                    await close_browser()
                    return True
                else:
                    console.print("[red]✗ فشل تسجيل الدخول[/red]")
                    await close_browser()
                    return False
                    
        except Exception as e:
            console.print(f"[red]✗ خطأ: {e}[/red]")
            return False
    
    async def _fill_email(self, page: Page) -> bool:
        """ملء حقل البريد الإلكتروني"""
        selectors = [
            'input[name="username"]',
            'input[type="email"]',
            '#username',
            'input[name="email"]'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.fill(CARFAX_EMAIL)
                    return True
            except:
                continue
                
        return False
    
    async def _fill_password(self, page: Page) -> bool:
        """ملء حقل كلمة المرور"""
        selectors = [
            'input[name="password"]',
            'input[type="password"]',
            '#password'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.fill(CARFAX_PASSWORD)
                    return True
            except:
                continue
                
        return False
    
    async def _click_submit(self, page: Page) -> bool:
        """النقر على زر الإرسال"""
        selectors = [
            'button[type="submit"]',
            'button[name="action"]',
            '.auth0-lock-submit',
            'input[type="submit"]'
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    return True
            except:
                continue
        
        # محاولة الضغط على Enter
        try:
            await page.keyboard.press("Enter")
            return True
        except:
            return False
    
    async def _verify_login(self, page: Page) -> bool:
        """
        التحقق من نجاح تسجيل الدخول
        
        Args:
            page: صفحة Playwright
            
        Returns:
            True إذا تم التسجيل بنجاح
        """
        try:
            # محاولة الوصول للصفحة الرئيسية
            await page.goto(CARFAX_BASE_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            
            # الحصول على محتوى الصفحة
            content = await page.content()
            html_lower = content.lower()
            
            # مؤشرات التسجيل الناجح
            logged_in_indicators = [
                "dealer home",
                "logged in",
                "welcome",
                "logout",
                "sign out",
                "my account"
            ]
            
            for indicator in logged_in_indicators:
                if indicator in html_lower:
                    return True
            
            # التحقق من URL
            current_url = page.url
            if "login" not in current_url.lower():
                return True
            
            return False
            
        except Exception as e:
            console.print(f"[red]  ⚠ خطأ في التحقق: {e}[/red]")
            return False
    
    async def _save_session_cookies(self, context) -> None:
        """
        حفظ cookies الجلسة بعد التسجيل
        
        Args:
            context: سياق Playwright
        """
        try:
            console.print("[dim]  → حفظ الجلسة...[/dim]")
            
            # الحصول على cookies من المتصفح
            cookies = await context.cookies()
            
            # تحديث مدير الـ cookies
            self.cookie_manager.update_from_playwright(cookies)
            
            # حفظ الـ cookies
            self.cookie_manager.save()
            
        except Exception as e:
            console.print(f"[yellow]  ⚠ تحذير في حفظ الـ cookies: {e}[/yellow]")


async def ensure_authenticated(cookie_manager: CookieManager) -> bool:
    """
    التأكد من وجود جلسة صالحة، وتسجيل الدخول إذا لزم الأمر
    
    Args:
        cookie_manager: مدير الـ cookies
        
    Returns:
        True إذا كانت الجلسة صالحة أو تم التسجيل بنجاح
    """
    # تحميل الـ cookies
    cookie_manager.load()
    
    # التحقق من صلاحية الجلسة
    if cookie_manager.is_session_valid():
        return True
    
    # محاولة تسجيل الدخول
    console.print("[yellow]⚠ الجلسة منتهية، جاري تسجيل الدخول...[/yellow]")
    
    auto_login = AutoLogin(cookie_manager)
    return await auto_login.login()
