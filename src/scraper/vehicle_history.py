"""
Vehicle History Scraper Module
==============================
سحب تقارير تاريخ المركبات من Carfax
"""

import asyncio
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncGenerator


from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from ..auth.cookies import CookieManager
from ..config import (
    CARFAX_BASE_URL,
    CARFAX_LOGIN_URL,
    CARFAX_EMAIL,
    CARFAX_PASSWORD,
    HEADLESS,
    MIN_DELAY,
    MAX_DELAY,
    USER_AGENT,
    PROXY_ENABLED,
    USE_CHROME_PROFILE,
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE,
    validate_credentials,
    get_playwright_proxy,
)

console = Console()


@dataclass
class VehicleReport:
    """نموذج بيانات تقرير المركبة"""
    
    vin: str
    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    owners: Optional[int] = None
    accidents: Optional[int] = None
    service_records: Optional[int] = None
    mileage: Optional[str] = None
    title_status: Optional[str] = None
    report_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    raw_data: dict = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """تحويل إلى قاموس"""
        return {
            "vin": self.vin,
            "year": self.year,
            "make": self.make,
            "model": self.model,
            "trim": self.trim,
            "owners": self.owners,
            "accidents": self.accidents,
            "service_records": self.service_records,
            "mileage": self.mileage,
            "title_status": self.title_status,
            "report_date": self.report_date,
            "error": self.error
        }


class VehicleHistoryScraper:
    """
    سحب تقارير تاريخ المركبات من Carfax
    
    يستخدم Playwright للوصول للصفحات المحمية
    واستخراج البيانات المطلوبة
    """
    
    # URLs
    VEHICLE_SEARCH_URL = f"{CARFAX_BASE_URL}"
    VEHICLE_REPORT_URL = f"{CARFAX_BASE_URL}"
    
    def __init__(self, cookie_manager: CookieManager):
        """
        تهيئة الـ Scraper
        
        Args:
            cookie_manager: مدير الـ cookies
        """
        self.cookie_manager = cookie_manager
        self._browser = None
        self._context = None
    
    async def _init_browser(self):
        """تهيئة المتصفح مع دعم البروكسي"""
        if self._browser is None:
            p = await async_playwright().start()
            self._browser = await p.chromium.launch(
                headless=HEADLESS,
                proxy=get_playwright_proxy()
            )
            self._context = await self._browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            
            # تحميل الـ cookies
            cookies = self.cookie_manager.get_cookies_for_playwright()
            if cookies:
                await self._context.add_cookies(cookies)
            
            if PROXY_ENABLED:
                console.print("[cyan]  🌐 المتصفح: البروكسي مفعل[/cyan]")
    
    async def _close_browser(self):
        """إغلاق المتصفح"""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
    
    async def get_report(self, vin: str) -> VehicleReport:
        """
        سحب تقرير مركبة واحدة
        
        Args:
            vin: رقم تعريف المركبة (VIN)
            
        Returns:
            تقرير المركبة
        """
        # التحقق من صحة VIN
        if not self._validate_vin(vin):
            return VehicleReport(vin=vin, error="VIN غير صالح")
        
        console.print(f"[blue]🔍 جاري البحث عن: {vin}[/blue]")
        
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
                    # استخدام Chrome المثبت مع الـ profile الحالي
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=os.path.join(CHROME_USER_DATA_DIR, CHROME_PROFILE),
                        channel="chrome",  # استخدام Chrome المثبت
                        headless=False,  # Chrome profile لا يعمل في headless
                        viewport={"width": 1920, "height": 1080},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox"
                        ]
                    )
                    browser = None  # لا يوجد browser منفصل
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
                    
                    # تحميل الـ cookies
                    cookies = self.cookie_manager.get_cookies_for_playwright()
                    if cookies:
                        await context.add_cookies(cookies)
                    
                    page = await context.new_page()
                
                # الذهاب للصفحة الرئيسية أولاً
                await page.goto(CARFAX_BASE_URL, wait_until="networkidle")
                await asyncio.sleep(2)
                
                # التحقق من حالة الجلسة وتسجيل الدخول إذا لزم
                html = await page.content()
                if self._is_login_required(html):
                    console.print("[yellow]  → جاري تسجيل الدخول...[/yellow]")
                    success = await self._login_in_browser(page)
                    if not success:
                        await browser.close()
                        return VehicleReport(vin=vin, error="فشل تسجيل الدخول")
                    await asyncio.sleep(2)
                
                # البحث عن حقل VIN وإدخاله
                vin_found = False
                try:
                    # انتظار تحميل الصفحة بالكامل
                    await asyncio.sleep(3)
                    
                    # انتظار ظهور حقل VIN
                    try:
                        await page.wait_for_selector('#vin', timeout=10000)
                    except:
                        console.print("[yellow]  ⚠ انتظار ظهور حقل VIN...[/yellow]")
                    
                    # استخدام Playwright's fill مع force
                    await page.click('#vin')
                    await asyncio.sleep(0.5)
                    
                    # مسح أي محتوى موجود
                    await page.fill('#vin', '')
                    await asyncio.sleep(0.3)
                    
                    # إدخال VIN
                    await page.fill('#vin', vin)
                    await asyncio.sleep(1)
                    
                    # التحقق من إدخال VIN
                    entered_value = await page.input_value('#vin')
                    console.print(f"[dim]  القيمة المدخلة: {entered_value}[/dim]")
                    
                    if entered_value == vin:
                        console.print(f"[green]  ✓ تم إدخال VIN بنجاح[/green]")
                        vin_found = True
                    else:
                        # محاولة ثانية باستخدام type
                        console.print("[yellow]  ⚠ محاولة إدخال VIN بطريقة أخرى...[/yellow]")
                        await page.click('#vin', click_count=3)  # تحديد الكل
                        await page.keyboard.type(vin, delay=100)
                        await asyncio.sleep(1)
                        entered_value = await page.input_value('#vin')
                        console.print(f"[dim]  القيمة بعد المحاولة الثانية: {entered_value}[/dim]")
                        vin_found = len(entered_value) > 0
                    
                    # انتظار تفعيل زر البحث
                    await asyncio.sleep(2)
                    
                    # التحقق من زر البحث
                    search_button = await page.query_selector('#run_vhr_button')
                    
                    if search_button:
                        is_disabled = await search_button.get_attribute('disabled')
                        console.print(f"[dim]  حالة الزر: {'معطل' if is_disabled else 'مفعل'}[/dim]")
                        
                        if is_disabled:
                            console.print("[yellow]  ⚠ الزر معطل - محاولة تفعيل...[/yellow]")
                            await asyncio.sleep(2)
                        
                        # النقر على الزر
                        console.print("[dim]  النقر على زر البحث...[/dim]")
                        url_before = page.url
                        
                        # النقر على الزر
                        await search_button.click()
                        console.print("[dim]  تم النقر - انتظار تحميل المحتوى...[/dim]")
                        
                        # انتظار تحميل المحتوى الجديد
                        await asyncio.sleep(3)
                        
                        url_after = page.url
                        
                        # إذا لم يتغير الـ URL، حاول الذهاب مباشرة لصفحة التقرير
                        if url_after == url_before:
                            console.print("[yellow]  ⚠ الـ URL لم يتغير - محاولة الانتقال مباشرة للتقرير...[/yellow]")
                            # جرب URLs مختلفة للتقرير
                            report_urls = [
                                f"{CARFAX_BASE_URL}/vhr/{vin}",
                                f"{CARFAX_BASE_URL}/cfm/vehicle-history-report.cfm?vin={vin}",
                                f"https://www.carfaxonline.com/vhr?vin={vin}",
                            ]
                            
                            for report_url in report_urls:
                                try:
                                    console.print(f"[dim]  محاولة: {report_url}[/dim]")
                                    await page.goto(report_url, wait_until="networkidle", timeout=15000)
                                    await asyncio.sleep(3)
                                    
                                    # تحقق إذا وصلنا لصفحة التقرير
                                    page_text = await page.inner_text('body')
                                    if vin in page_text or "Previous owner" in page_text or "accident" in page_text.lower():
                                        console.print("[green]  ✓ تم العثور على صفحة التقرير![/green]")
                                        break
                                except Exception as nav_err:
                                    console.print(f"[dim]  فشل: {nav_err}[/dim]")
                                    continue
                        
                        # البحث عن عناصر التقرير أو رسائل الخطأ
                        page_text = await page.inner_text('body')
                        has_report = vin in page_text or "Previous owner" in page_text or "accident" in page_text.lower()
                    
                    # انتظار تحميل النتائج
                    console.print("[dim]  انتظار تحميل التقرير...[/dim]")
                    await asyncio.sleep(3)
                    
                    current_url = page.url
                    console.print(f"[dim]  URL الحالي: {current_url}[/dim]")
                    
                except Exception as e:
                    console.print(f"[yellow]  ⚠ خطأ في إدخال VIN: {e}[/yellow]")
                
                # الحصول على HTML
                html = await page.content()
                
                # استخراج البيانات
                report = self._extract_report_data(vin, html)
                
                # حفظ HTML للتصحيح
                debug_file = Path(f"data/debug_{vin}.html")
                debug_file.parent.mkdir(exist_ok=True)
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(html)
                console.print(f"[dim]  تم حفظ HTML في: {debug_file}[/dim]")
                
                # إغلاق المتصفح
                if USE_CHROME_PROFILE:
                    await context.close()
                else:
                    await browser.close()
                
                # تأخير عشوائي
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                
                return report
                
        except Exception as e:
            console.print(f"[red]✗ خطأ: {e}[/red]")
            return VehicleReport(vin=vin, error=str(e))
    
    async def get_reports(
        self, 
        vins: list[str],
        progress_callback: Optional[callable] = None
    ) -> AsyncGenerator[VehicleReport, None]:
        """
        سحب تقارير متعددة
        
        Args:
            vins: قائمة أرقام VIN
            progress_callback: دالة لتتبع التقدم
            
        Yields:
            تقارير المركبات
        """
        total = len(vins)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]سحب {total} تقرير...", total=total)
            
            for i, vin in enumerate(vins):
                report = await self.get_report(vin)
                
                progress.update(task, advance=1)
                
                if progress_callback:
                    progress_callback(i + 1, total, report)
                
                yield report
    
    async def _login_in_browser(self, page: Page) -> bool:
        """تسجيل الدخول داخل المتصفح"""
        if not validate_credentials():
            console.print("[red]  ✗ بيانات الاعتماد غير موجودة[/red]")
            return False
        
        try:
            # الذهاب لصفحة تسجيل الدخول
            await page.goto(CARFAX_LOGIN_URL, wait_until="networkidle")
            await asyncio.sleep(2)
            
            # ملء البريد الإلكتروني
            email_selectors = ['input[name="username"]', 'input[type="email"]', '#username']
            for selector in email_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        await elem.fill(CARFAX_EMAIL)
                        break
                except:
                    continue
            
            await asyncio.sleep(0.5)
            
            # ملء كلمة المرور
            pass_selectors = ['input[name="password"]', 'input[type="password"]', '#password']
            for selector in pass_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        await elem.fill(CARFAX_PASSWORD)
                        break
                except:
                    continue
            
            await asyncio.sleep(0.5)
            
            # النقر على زر الإرسال
            submit_selectors = ['button[type="submit"]', 'button[name="action"]']
            for selector in submit_selectors:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        await elem.click()
                        break
                except:
                    continue
            
            # انتظار التوجيه
            await asyncio.sleep(5)
            
            # التحقق من نجاح التسجيل
            html = await page.content()
            if "logout" in html.lower() or "sign out" in html.lower():
                console.print("[green]  ✓ تم تسجيل الدخول[/green]")
                return True
            
            return True  # نفترض النجاح
            
        except Exception as e:
            console.print(f"[red]  ✗ خطأ في تسجيل الدخول: {e}[/red]")
            return False
    
    def _validate_vin(self, vin: str) -> bool:
        """
        التحقق من صحة VIN
        
        Args:
            vin: رقم VIN
            
        Returns:
            True إذا كان صالحاً
        """
        if not vin:
            return False
            
        # VIN يجب أن يكون 17 حرفاً
        vin = vin.strip().upper()
        if len(vin) != 17:
            console.print(f"[yellow]  ⚠ VIN يجب أن يكون 17 حرفاً: {vin}[/yellow]")
            return False
            
        # لا يحتوي على I, O, Q
        if any(c in vin for c in "IOQ"):
            console.print(f"[yellow]  ⚠ VIN لا يجب أن يحتوي I, O, Q: {vin}[/yellow]")
            return False
            
        return True
    
    def _is_login_required(self, html: str) -> bool:
        """
        التحقق إذا كانت الصفحة تطلب تسجيل الدخول
        
        Args:
            html: محتوى الصفحة
            
        Returns:
            True إذا كان التسجيل مطلوباً
        """
        html_lower = html.lower()
        
        # التحقق من عنوان الصفحة - هذا هو المؤشر الأفضل
        if "dealer account sign in" in html_lower:
            return True
        
        # التحقق من وجود رابط Sign In (وليس زر Logout)
        if 'href="/login"' in html_lower and "logout" not in html_lower:
            return True
            
        # إذا كانت صفحة الهبوط landing page
        if "landingpage" in html_lower or "get the most info now" in html_lower:
            return True
        
        # إذا وجدنا مؤشرات الجلسة النشطة
        logged_in_indicators = [
            "sign out",  
            "logout button",
            "run vin",
            "vehicle history"
        ]
        
        for indicator in logged_in_indicators:
            if indicator in html_lower:
                return False
                
        return False
    
    def _extract_report_data(self, vin: str, html: str) -> VehicleReport:
        """
        استخراج بيانات التقرير من HTML
        
        Args:
            vin: رقم VIN
            html: محتوى الصفحة
            
        Returns:
            تقرير المركبة
        """
        report = VehicleReport(vin=vin)
        
        # التحقق من الأخطاء
        if "unexpected error has occurred" in html.lower():
            report.error = "خطأ في الموقع - VIN قد يكون غير صالح"
            console.print(f"[red]  ✗ خطأ من الموقع - تحقق من VIN[/red]")
            return report
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # استخراج السنة/الشركة/الموديل من عنوان التقرير
            # مثال: "2008 BMW 3 SERIES 328XI"
            ymm = self._extract_year_make_model(html, soup)
            if ymm:
                report.year = ymm.get("year")
                report.make = ymm.get("make")
                report.model = ymm.get("model")
                report.trim = ymm.get("trim")
            
            # استخراج عدد الملاك
            report.owners = self._extract_owners(html, soup)
            
            # استخراج الحوادث
            report.accidents = self._extract_accidents(html, soup)
            
            # استخراج سجلات الخدمة
            report.service_records = self._extract_service_records(html, soup)
            
            # استخراج المسافة (Last reported odometer reading)
            report.mileage = self._extract_mileage(html, soup)
            
            # استخراج حالة العنوان
            report.title_status = self._extract_title_status(html, soup)
            
            # استخراج بيانات إضافية من التقرير
            report.raw_data = self._extract_additional_data(html, soup)
            
            if report.year or report.make or report.model:
                vehicle_info = f"{report.year or '?'} {report.make or '?'} {report.model or '?'}"
                if report.trim:
                    vehicle_info += f" {report.trim}"
                console.print(f"[green]  ✓ {vehicle_info}[/green]")
                
                # عرض ملخص البيانات
                if report.owners:
                    console.print(f"[dim]    الملاك: {report.owners}[/dim]")
                if report.accidents is not None:
                    console.print(f"[dim]    الحوادث: {report.accidents}[/dim]")
                if report.mileage:
                    console.print(f"[dim]    المسافة: {report.mileage} miles[/dim]")
                if report.service_records:
                    console.print(f"[dim]    سجلات الخدمة: {report.service_records}[/dim]")
            else:
                console.print(f"[yellow]  ⚠ لم يتم العثور على بيانات المركبة[/yellow]")
            
        except Exception as e:
            report.error = f"خطأ في الاستخراج: {e}"
            console.print(f"[red]  ✗ خطأ في الاستخراج: {e}[/red]")
            
        return report
    
    def _extract_additional_data(self, html: str, soup: BeautifulSoup) -> dict:
        """استخراج بيانات إضافية من التقرير"""
        data = {}
        
        # استخراج CARFAX Retail Value
        value_match = re.search(r'\$[\d,]+(?:\.\d{2})?\s*(?:CARFAX\s*Retail\s*Value)?', html)
        if value_match:
            data['retail_value'] = value_match.group(0).strip()
        
        # استخراج نوع المركبة (SEDAN, SUV, etc.)
        vehicle_types = ['SEDAN', 'SUV', 'COUPE', 'TRUCK', 'VAN', 'WAGON', 'CONVERTIBLE', 'HATCHBACK']
        for vtype in vehicle_types:
            if vtype in html.upper():
                data['vehicle_type'] = vtype
                break
        
        # استخراج نوع الوقود
        fuel_types = ['GASOLINE', 'DIESEL', 'ELECTRIC', 'HYBRID', 'FLEX FUEL']
        for ftype in fuel_types:
            if ftype in html.upper():
                data['fuel_type'] = ftype
                break
        
        # استخراج نظام الدفع
        drive_types = ['ALL WHEEL DRIVE', 'FRONT WHEEL DRIVE', 'REAR WHEEL DRIVE', '4WD', 'AWD', 'FWD', 'RWD']
        for dtype in drive_types:
            if dtype in html.upper():
                data['drive_type'] = dtype
                break
        
        # استخراج الولاية الأخيرة
        state_match = re.search(r'Last owned in\s+([A-Za-z\s]+)', html)
        if state_match:
            data['last_state'] = state_match.group(1).strip()
        
        return data
    
    def _extract_year_make_model(self, html: str, soup: BeautifulSoup) -> Optional[dict]:
        """استخراج السنة/الشركة/الموديل"""
        
        # قائمة الشركات المعروفة للتحقق
        known_makes = [
            'Honda', 'Toyota', 'Ford', 'Chevrolet', 'Chevy', 'BMW', 'Mercedes', 
            'Audi', 'Volkswagen', 'VW', 'Nissan', 'Hyundai', 'Kia', 'Mazda',
            'Subaru', 'Lexus', 'Acura', 'Infiniti', 'Jeep', 'Dodge', 'Ram',
            'Chrysler', 'GMC', 'Cadillac', 'Buick', 'Lincoln', 'Volvo', 'Porsche',
            'Tesla', 'Mitsubishi', 'Suzuki', 'Fiat', 'Alfa', 'Jaguar', 'Land',
            'Range', 'Mini', 'Smart', 'Scion', 'Saturn', 'Pontiac', 'Oldsmobile',
            'Mercury', 'Hummer', 'Saab', 'Isuzu', 'Daewoo', 'Genesis', 'Polestar'
        ]
        known_makes_lower = [m.lower() for m in known_makes]
        
        # البحث في العناصر المحددة
        title_elements = soup.select('.vehicle-title, .vehicle-header, [class*="year-make-model"], .vhr-title, .report-title')
        
        for elem in title_elements:
            text = elem.get_text(strip=True)
            match = re.match(r'(\d{4})\s+([A-Za-z]+)\s+(.+)', text)
            if match:
                make = match.group(2)
                # تحقق أن الشركة معروفة
                if make.lower() in known_makes_lower:
                    return {
                        "year": match.group(1),
                        "make": make,
                        "model": match.group(3).split()[0] if match.group(3) else None,
                        "trim": " ".join(match.group(3).split()[1:]) if len(match.group(3).split()) > 1 else None
                    }
        
        # البحث بنمط أكثر تحديداً - السنة + شركة معروفة
        for make in known_makes:
            pattern = rf'(\d{{4}})\s+{make}\s+([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)'
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return {
                    "year": match.group(1),
                    "make": make,
                    "model": match.group(2).split()[0] if match.group(2) else None,
                    "trim": " ".join(match.group(2).split()[1:]) if len(match.group(2).split()) > 1 else None
                }
        
        # البحث عن سنة فقط في عناصر التقرير
        year_elements = soup.select('[class*="year"], [class*="vehicle"]')
        for elem in year_elements:
            text = elem.get_text(strip=True)
            match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text)
            if match:
                year = match.group(1)
                # تحقق أنها سنة منطقية للمركبة (1980-2025)
                if 1980 <= int(year) <= 2026:
                    return {"year": year}
                    
        return None
    
    def _extract_owners(self, html: str, soup: BeautifulSoup) -> Optional[int]:
        """استخراج عدد الملاك"""
        # أنماط محددة من تقرير CARFAX
        patterns = [
            r'(\d+)\s*Previous\s*owners?',  # "2 Previous owners"
            r'(\d+)\s*owner',  # "2 owner"
            r'owner[s]?["\s:>]+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        # البحث في العناصر
        owner_elements = soup.select('[class*="owner"], .ownership-history')
        for elem in owner_elements:
            text = elem.get_text()
            match = re.search(r'(\d+)\s*(?:Previous\s*)?owner', text, re.IGNORECASE)
            if match:
                return int(match.group(1))
                    
        return None
    
    def _extract_accidents(self, html: str, soup: BeautifulSoup) -> Optional[int]:
        """استخراج عدد الحوادث"""
        # البحث عن "No accidents" أولاً
        if re.search(r'no\s*accident', html, re.IGNORECASE):
            return 0
        
        # البحث في العناصر
        accident_elements = soup.select('[class*="accident"]')
        for elem in accident_elements:
            text = elem.get_text()
            if 'no accident' in text.lower():
                return 0
            match = re.search(r'(\d+)\s*accident', text, re.IGNORECASE)
            if match:
                return int(match.group(1))
            
        patterns = [
            r'(\d+)\s*accident',
            r'accident[s]?["\s:>]+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
                    
        return None
    
    def _extract_service_records(self, html: str, soup: BeautifulSoup) -> Optional[int]:
        """استخراج عدد سجلات الخدمة"""
        patterns = [
            r'(\d+)\s*Service\s*history\s*records?',  # "38 Service history records"
            r'(\d+)\s*service\s*records?',
            r'service.*?(\d+)\s*records?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
                    
        return None
    
    def _extract_mileage(self, html: str, soup: BeautifulSoup) -> Optional[str]:
        """استخراج قراءة عداد المسافات"""
        # أنماط محددة من تقرير CARFAX
        patterns = [
            r'([\d,]+)\s*Last\s*reported\s*odometer\s*reading',  # "108,487 Last reported odometer reading"
            r'Last\s*reported\s*odometer\s*reading[:\s]*([\d,]+)',
            r'odometer[:\s]*([\d,]+)',
            r'([\d,]+)\s*(?:miles|mi)\b',
            r'mileage[:\s]*([\d,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                mileage = match.group(1).replace(',', '')
                # تحقق أن الرقم منطقي (أكثر من 100 وأقل من مليون)
                try:
                    if 100 < int(mileage) < 1000000:
                        return match.group(1)  # إرجاع مع الفواصل
                except:
                    pass
        
        # البحث في العناصر
        mileage_elements = soup.select('[class*="mileage"], [class*="odometer"]')
        for elem in mileage_elements:
            text = elem.get_text()
            match = re.search(r'([\d,]+)', text)
            if match:
                mileage = match.group(1).replace(',', '')
                try:
                    if 100 < int(mileage) < 1000000:
                        return match.group(1)
                except:
                    pass
                    
        return None
    
    def _extract_title_status(self, html: str, soup: BeautifulSoup) -> Optional[str]:
        """استخراج حالة العنوان"""
        statuses = [
            ("clean title", "Clean"),
            ("salvage", "Salvage"),
            ("rebuilt", "Rebuilt"),
            ("flood", "Flood"),
            ("lemon", "Lemon"),
            ("junk", "Junk"),
        ]
        
        html_lower = html.lower()
        
        for pattern, status in statuses:
            if pattern in html_lower:
                return status
                
        return None


async def scrape_single_vin(
    vin: str, 
    cookie_manager: CookieManager
) -> VehicleReport:
    """
    دالة مساعدة لسحب تقرير مركبة واحدة
    
    Args:
        vin: رقم VIN
        cookie_manager: مدير الـ cookies
        
    Returns:
        تقرير المركبة
    """
    scraper = VehicleHistoryScraper(cookie_manager)
    return await scraper.get_report(vin)


async def scrape_multiple_vins(
    vins: list[str],
    cookie_manager: CookieManager
) -> list[VehicleReport]:
    """
    دالة مساعدة لسحب تقارير متعددة
    
    Args:
        vins: قائمة أرقام VIN
        cookie_manager: مدير الـ cookies
        
    Returns:
        قائمة التقارير
    """
    scraper = VehicleHistoryScraper(cookie_manager)
    reports = []
    
    async for report in scraper.get_reports(vins):
        reports.append(report)
        
    return reports
