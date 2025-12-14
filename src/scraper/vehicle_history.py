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
    validate_credentials,
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
        """تهيئة المتصفح"""
        if self._browser is None:
            p = await async_playwright().start()
            self._browser = await p.chromium.launch(headless=HEADLESS)
            self._context = await self._browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            
            # تحميل الـ cookies
            cookies = self.cookie_manager.get_cookies_for_playwright()
            if cookies:
                await self._context.add_cookies(cookies)
    
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
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=HEADLESS)
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080}
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
                    # البحث عن حقل الإدخال - جرب عدة selectors
                    vin_selectors = [
                        'input[name="vin"]',
                        'input[placeholder*="VIN"]',
                        'input[id*="vin"]',
                        '#vinInput',
                        'input[aria-label*="VIN"]',
                        'input[class*="vin"]',
                        'input[type="text"]'
                    ]
                    
                    for selector in vin_selectors:
                        vin_input = await page.query_selector(selector)
                        if vin_input:
                            await vin_input.click()
                            await asyncio.sleep(0.3)
                            await vin_input.fill(vin)
                            await asyncio.sleep(0.5)
                            console.print(f"[dim]  تم إدخال VIN في: {selector}[/dim]")
                            vin_found = True
                            break
                    
                    if vin_found:
                        # البحث عن زر البحث والنقر عليه
                        button_selectors = [
                            'button[type="submit"]',
                            'button:has-text("Run")',
                            'button:has-text("Search")',
                            'button:has-text("Go")',
                            '.search-btn',
                            'input[type="submit"]'
                        ]
                        
                        for selector in button_selectors:
                            try:
                                search_button = await page.query_selector(selector)
                                if search_button:
                                    await search_button.click()
                                    console.print(f"[dim]  تم النقر على: {selector}[/dim]")
                                    await asyncio.sleep(5)
                                    break
                            except:
                                continue
                        
                        # أو اضغط Enter
                        if not search_button:
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(5)
                            
                except Exception as e:
                    console.print(f"[yellow]  ⚠ لم يتم العثور على حقل VIN: {e}[/yellow]")
                
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
            
            # استخراج السنة/الشركة/الموديل
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
            
            # استخراج المسافة
            report.mileage = self._extract_mileage(html, soup)
            
            # استخراج حالة العنوان
            report.title_status = self._extract_title_status(html, soup)
            
            if report.year or report.make or report.model:
                console.print(f"[green]  ✓ {report.year or '?'} {report.make or '?'} {report.model or '?'}[/green]")
            else:
                console.print(f"[yellow]  ⚠ لم يتم العثور على بيانات المركبة[/yellow]")
            
        except Exception as e:
            report.error = f"خطأ في الاستخراج: {e}"
            console.print(f"[red]  ✗ خطأ في الاستخراج: {e}[/red]")
            
        return report
    
    def _extract_year_make_model(self, html: str, soup: BeautifulSoup) -> Optional[dict]:
        """استخراج السنة/الشركة/الموديل"""
        # البحث في العناصر المحددة
        title_elements = soup.select('.vehicle-title, .vehicle-header, [class*="year-make-model"]')
        
        for elem in title_elements:
            text = elem.get_text(strip=True)
            match = re.match(r'(\d{4})\s+([A-Za-z]+)\s+(.+)', text)
            if match:
                return {
                    "year": match.group(1),
                    "make": match.group(2),
                    "model": match.group(3).split()[0] if match.group(3) else None,
                    "trim": " ".join(match.group(3).split()[1:]) if len(match.group(3).split()) > 1 else None
                }
        
        # البحث بالنمط في HTML
        patterns = [
            r'(\d{4})\s+([A-Za-z]+)\s+([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)\s*([A-Za-z0-9]*)',
            r'year["\s:>]+(\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    return {
                        "year": groups[0],
                        "make": groups[1],
                        "model": groups[2],
                        "trim": groups[3] if len(groups) > 3 else None
                    }
                elif len(groups) == 1:
                    return {"year": groups[0]}
                    
        return None
    
    def _extract_owners(self, html: str, soup: BeautifulSoup) -> Optional[int]:
        """استخراج عدد الملاك"""
        # البحث في العناصر
        owner_elements = soup.select('[class*="owner"], .ownership-history')
        for elem in owner_elements:
            text = elem.get_text()
            match = re.search(r'(\d+)\s*owner', text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # البحث بالنمط
        patterns = [
            r'(\d+)\s*owner',
            r'owner[s]?["\s:>]+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
                    
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
            r'(\d+)\s*service\s*record',
            r'service.*?(\d+)\s*record',
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
        # البحث في العناصر
        mileage_elements = soup.select('[class*="mileage"], [class*="odometer"]')
        for elem in mileage_elements:
            text = elem.get_text()
            match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|mi)', text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        patterns = [
            r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|mi)',
            r'odometer.*?(\d{1,3}(?:,\d{3})*)',
            r'mileage.*?(\d{1,3}(?:,\d{3})*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
                    
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
