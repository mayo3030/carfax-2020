"""
Full CARFAX Report Scraper
==========================
استخراج كل بيانات تقرير CARFAX وتصديرها إلى JSON و CSV
"""

import asyncio
import json
import re
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from rich.console import Console

from ..config import (
    CARFAX_BASE_URL,
    USE_CHROME_PROFILE,
    CHROME_USER_DATA_DIR,
    CHROME_PROFILE,
)

console = Console()


@dataclass
class ServiceRecord:
    """سجل خدمة واحد"""
    date: str = ""
    mileage: str = ""
    source: str = ""
    location: str = ""
    comments: List[str] = field(default_factory=list)


@dataclass
class OwnerHistory:
    """تاريخ مالك واحد"""
    owner_number: int = 0
    year_purchased: str = ""
    owner_type: str = ""
    length_of_ownership: str = ""
    states: List[str] = field(default_factory=list)
    miles_per_year: str = ""
    last_odometer: str = ""
    service_records: List[ServiceRecord] = field(default_factory=list)


@dataclass
class FullCarfaxReport:
    """تقرير CARFAX الكامل"""
    # معلومات أساسية
    vin: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    trim: str = ""
    body_type: str = ""
    engine: str = ""
    fuel_type: str = ""
    drive_type: str = ""
    
    # ملخص التقرير - الأسعار
    retail_value: str = ""
    wholesale_value: str = ""
    trade_in_value: str = ""
    private_party_value: str = ""
    
    total_owners: int = 0
    accidents_reported: int = 0
    damage_reported: bool = False
    service_records_count: int = 0
    last_odometer: str = ""
    last_state: str = ""
    
    # حالة العنوان
    title_status: str = ""
    total_loss: str = ""
    structural_damage: str = ""
    airbag_deployment: str = ""
    odometer_status: str = ""
    
    # ضمانات
    basic_warranty: str = ""
    recalls: str = ""
    
    # تاريخ الملاك
    owners: List[OwnerHistory] = field(default_factory=list)
    
    # سجلات الخدمة التفصيلية
    detailed_history: List[Dict] = field(default_factory=list)
    
    # بيانات إضافية
    report_date: str = ""
    error: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس"""
        return asdict(self)
    
    def to_json(self, filepath: str = None) -> str:
        """تصدير إلى JSON"""
        data = self.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        
        if filepath:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)
            console.print(f"[green]✓ تم حفظ JSON: {filepath}[/green]")
        
        return json_str
    
    def to_csv_row(self) -> Dict[str, str]:
        """تحويل إلى صف CSV (البيانات الأساسية فقط)"""
        return {
            "vin": self.vin,
            "year": self.year,
            "make": self.make,
            "model": self.model,
            "trim": self.trim,
            "body_type": self.body_type,
            "engine": self.engine,
            "fuel_type": self.fuel_type,
            "drive_type": self.drive_type,
            "retail_value": self.retail_value,
            "wholesale_value": self.wholesale_value,
            "trade_in_value": self.trade_in_value,
            "private_party_value": self.private_party_value,
            "total_owners": str(self.total_owners),
            "accidents_reported": str(self.accidents_reported),
            "service_records_count": str(self.service_records_count),
            "last_odometer": self.last_odometer,
            "last_state": self.last_state,
            "title_status": self.title_status,
            "total_loss": self.total_loss,
            "structural_damage": self.structural_damage,
            "airbag_deployment": self.airbag_deployment,
            "odometer_status": self.odometer_status,
            "basic_warranty": self.basic_warranty,
            "recalls": self.recalls,
            "report_date": self.report_date,
            "error": self.error
        }


class FullReportScraper:
    """
    Scraper شامل لاستخراج كل بيانات تقرير CARFAX
    
    يستخدم Playwright للوصول للصفحة و BeautifulSoup للتحليل
    """
    
    def __init__(self):
        self.report = None
    
    async def scrape_report(self, vin: str, get_wholesale: bool = True, fast_mode: bool = False) -> FullCarfaxReport:
        """
        سحب التقرير الكامل لـ VIN
        
        Args:
            vin: رقم VIN
            get_wholesale: هل نحاول الحصول على سعر الـ Wholesale
            fast_mode: وضع سريع (بدون حفظ debug files)
            
        Returns:
            تقرير CARFAX الكامل
        """
        console.print(f"[blue]🔍 جاري سحب التقرير الكامل لـ: {vin}[/blue]")
        if fast_mode:
            console.print("[yellow]  ⚡ الوضع السريع[/yellow]")
        
        report = FullCarfaxReport(vin=vin, report_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        try:
            async with async_playwright() as p:
                # إطلاق المتصفح مع Chrome Profile
                use_headless = fast_mode  # استخدام headless في الوضع السريع
                
                if USE_CHROME_PROFILE:
                    console.print("[cyan]  🌐 استخدام Chrome Profile[/cyan]")
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=os.path.join(CHROME_USER_DATA_DIR, CHROME_PROFILE),
                        channel="chrome",
                        headless=use_headless,
                        viewport={"width": 1920, "height": 1080},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                            "--disable-gpu" if use_headless else "",
                            "--disable-images" if fast_mode else "",  # تعطيل الصور في الوضع السريع
                        ] + (["--disable-extensions"] if fast_mode else [])
                    )
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    browser = await p.chromium.launch(headless=use_headless)
                    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = await context.new_page()
                
                # في الوضع السريع: حجب الموارد غير الضرورية (صور، خطوط، فيديو)
                # لا نحجب CSS/JS لأنها قد تكون مطلوبة لعرض البيانات
                if fast_mode:
                    async def route_handler(route):
                        resource_type = route.request.resource_type
                        if resource_type in ["image", "font", "media"]:
                            await route.abort()
                        else:
                            await route.continue_()
                    await context.route("**/*", route_handler)
                
                # الذهاب مباشرة لصفحة التقرير
                report_url = f"{CARFAX_BASE_URL}/vhr/{vin}"
                console.print(f"[dim]  → الذهاب إلى: {report_url}[/dim]")
                
                # استخدام domcontentloaded بدلاً من networkidle (أسرع بكثير)
                await page.goto(report_url, wait_until="domcontentloaded", timeout=20000)
                
                # انتظار تحميل البيانات المهمة (JSON المضمن)
                try:
                    # انتظار وجود VIN أو wholesalePrice في الصفحة (أسرع من networkidle)
                    await page.wait_for_function(
                        f'() => document.body && (document.body.innerText.includes("{vin}") || document.body.innerHTML.includes("wholesalePrice"))',
                        timeout=8000
                    )
                except:
                    # إذا لم ينجح، ننتظر قليلاً فقط
                    await asyncio.sleep(0.8)
                
                # محاولة استخراج JSON مباشرة من JavaScript (أسرع)
                json_data = None
                try:
                    json_data = await page.evaluate("""
                        () => {
                            // البحث عن window.__INITIAL_STATE__ أو بيانات مشابهة
                            if (window.__INITIAL_STATE__) return window.__INITIAL_STATE__;
                            if (window.__NEXT_DATA__) return window.__NEXT_DATA__;
                            // البحث في script tags
                            const scripts = document.querySelectorAll('script[type="application/json"]');
                            for (let script of scripts) {
                                try {
                                    return JSON.parse(script.textContent);
                                } catch(e) {}
                            }
                            return null;
                        }
                    """)
                except:
                    pass
                
                # الحصول على HTML
                html = await page.content()
                
                # إذا حصلنا على JSON مباشرة، نضيفه للـ HTML لاستخراجه لاحقاً
                if json_data:
                    html += f"\n<!-- JSON_DATA: {json.dumps(json_data)} -->"
                
                # التحقق من وجود VIN أو wholesalePrice في الصفحة
                if vin not in html and 'wholesalePrice' not in html:
                    console.print("[yellow]  ⚠ انتظار تحميل البيانات...[/yellow]")
                    await asyncio.sleep(1)  # تقليل من 2 إلى 1 ثانية
                    html = await page.content()
                
                # لا حاجة للنقر - الأسعار موجودة في JSON المضمن في HTML
                
                # حفظ HTML للتصحيح (في الوضع العادي فقط)
                if not fast_mode:
                    debug_file = Path(f"data/full_report_{vin}.html")
                    debug_file.parent.mkdir(exist_ok=True)
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(html)
                    console.print(f"[dim]  تم حفظ HTML: {debug_file}[/dim]")
                
                # استخراج البيانات
                report = self._extract_full_report(vin, html)
                
                # إغلاق المتصفح
                await context.close()
                
        except Exception as e:
            console.print(f"[red]✗ خطأ: {e}[/red]")
            report.error = str(e)
        
        return report
    
    async def _click_wholesale_prices(self, page) -> bool:
        """
        النقر على أزرار عرض الأسعار المختلفة (Wholesale, Trade-In, Private Party)
        
        Returns:
            True إذا نجح النقر
        """
        try:
            console.print("[dim]  → البحث عن أزرار الأسعار...[/dim]")
            
            # قائمة الـ selectors المحتملة لأزرار الأسعار
            price_buttons = [
                # Wholesale buttons
                'button:has-text("Wholesale")',
                '[data-testid*="wholesale"]',
                '[class*="wholesale"]',
                'a:has-text("Wholesale")',
                # Trade-In buttons
                'button:has-text("Trade-In")',
                'button:has-text("Trade In")',
                '[data-testid*="trade"]',
                # Value tabs
                '[class*="value-tab"]',
                '[class*="price-tab"]',
                'button[class*="tab"]',
                # History-Based Value
                'button:has-text("Value")',
                '[class*="hbv"]',
            ]
            
            clicked = False
            for selector in price_buttons:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            await element.click()
                            console.print(f"[green]  ✓ تم النقر على: {selector}[/green]")
                            clicked = True
                            await asyncio.sleep(1)
                except:
                    continue
            
            # محاولة النقر على History-Based Value section لتوسيعها
            try:
                hbv_section = await page.query_selector('[class*="history-based"], [class*="hbv"], .value-section')
                if hbv_section:
                    await hbv_section.click()
                    console.print("[dim]  → توسيع قسم القيمة...[/dim]")
                    await asyncio.sleep(1)
            except:
                pass
            
            # البحث عن dropdown أو select للأسعار
            try:
                price_dropdown = await page.query_selector('select[class*="value"], select[class*="price"]')
                if price_dropdown:
                    # اختيار Wholesale
                    await page.select_option(price_dropdown, label="Wholesale")
                    console.print("[green]  ✓ تم اختيار Wholesale من القائمة[/green]")
                    clicked = True
            except:
                pass
            
            return clicked
            
        except Exception as e:
            console.print(f"[dim]  ⚠ لم يتم العثور على أزرار الأسعار: {e}[/dim]")
            return False
    
    def _extract_all_prices(self, report: FullCarfaxReport, html: str, text: str) -> None:
        """
        استخراج جميع أنواع الأسعار من الصفحة
        
        Args:
            report: كائن التقرير لتحديثه
            html: الـ HTML الخام
            text: النص المستخرج
        """
        # 1. Retail Value (السعر الأساسي) - من JSON المضمن
        retail_patterns = [
            r'"carfaxPrice"\s*:\s*"\$?([\d,]+)"',  # JSON format
            r'"retailPrice"\s*:\s*"\$?([\d,]+)"',  # Alternative JSON
            r'"value"\s*:\s*"\$?([\d,]+)"[^}]*"text"\s*:\s*"[^"]*Retail',  # Value with Retail label
            r'(?:CARFAX\s+)?Retail\s+Value[:\s]*\$\s*([\d,]+)',
            r'\$\s*([\d,]+)\s*(?:CARFAX\s+)?Retail',
        ]
        for pattern in retail_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                report.retail_value = f"${match.group(1)}"
                break
        
        # إذا لم نجد بنمط محدد، نبحث عن أول سعر
        if not report.retail_value:
            simple_match = re.search(r'\$\s*([\d,]+)', html)
            if simple_match:
                report.retail_value = f"${simple_match.group(1)}"
        
        # 2. Wholesale Value (سعر الجملة) - من JSON المضمن
        wholesale_patterns = [
            r'"wholesalePrice"\s*:\s*"\$?([\d,]+)"',  # JSON format (الأكثر دقة)
            r'"value"\s*:\s*"\$?([\d,]+)"[^}]*"text"\s*:\s*"[^"]*Wholesale',  # Value with Wholesale label
            r'Wholesale\s+Value[:\s]*\$\s*([\d,]+)',
            r'\$\s*([\d,]+)\s*Wholesale',
        ]
        for pattern in wholesale_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                report.wholesale_value = f"${match.group(1)}"
                break
        
        # 3. Trade-In Value (قيمة الاستبدال)
        trade_patterns = [
            r'"tradeInPrice"\s*:\s*"\$?([\d,]+)"',  # JSON format
            r'"value"\s*:\s*"\$?([\d,]+)"[^}]*"text"\s*:\s*"[^"]*Trade[\s-]?In',  # Value with Trade-In label
            r'Trade[\s-]?In\s+Value[:\s]*\$\s*([\d,]+)',
            r'\$\s*([\d,]+)\s*Trade[\s-]?In',
        ]
        for pattern in trade_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                report.trade_in_value = f"${match.group(1)}"
                break
        
        # 4. Private Party Value (البيع الخاص)
        private_patterns = [
            r'"privatePartyPrice"\s*:\s*"\$?([\d,]+)"',  # JSON format
            r'"value"\s*:\s*"\$?([\d,]+)"[^}]*"text"\s*:\s*"[^"]*Private\s+Party',  # Value with label
            r'Private\s+Party\s+Value[:\s]*\$\s*([\d,]+)',
            r'\$\s*([\d,]+)\s*Private\s+Party',
        ]
        for pattern in private_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                report.private_party_value = f"${match.group(1)}"
                break
        
        # طباعة الأسعار المستخرجة
        console.print(f"[dim]    💰 Retail: {report.retail_value or 'N/A'}[/dim]")
        if report.wholesale_value:
            console.print(f"[dim]    💵 Wholesale: {report.wholesale_value}[/dim]")
        if report.trade_in_value:
            console.print(f"[dim]    🔄 Trade-In: {report.trade_in_value}[/dim]")
        if report.private_party_value:
            console.print(f"[dim]    👤 Private Party: {report.private_party_value}[/dim]")
    
    def _extract_full_report(self, vin: str, html: str) -> FullCarfaxReport:
        """استخراج كل البيانات من HTML"""
        report = FullCarfaxReport(vin=vin, report_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(" ", strip=True)
        
        console.print("[dim]  → استخراج البيانات...[/dim]")
        
        # ==========================================
        # 1. معلومات المركبة الأساسية
        # ==========================================
        
        # استخراج السنة/الشركة/الموديل من عنوان الصفحة
        title_match = re.search(r'(\d{4})\s+([A-Z]+)\s+(\d+\s+SERIES\s+[A-Z0-9]+)', html, re.IGNORECASE)
        if title_match:
            report.year = title_match.group(1)
            report.make = title_match.group(2)
            report.model = title_match.group(3).strip()
        else:
            # محاولة ثانية - البحث عن نمط أبسط
            title_match = re.search(r'(\d{4})\s+([A-Z]+)\s+([A-Z0-9\s]+?)(?:VIN|"|\n)', html, re.IGNORECASE)
            if title_match:
                report.year = title_match.group(1)
                report.make = title_match.group(2)
                model_part = title_match.group(3).strip()
                # تنظيف النص من أي JSON
                model_part = re.sub(r'["{}\[\]:,].*$', '', model_part).strip()
                if len(model_part) < 50:  # تجنب النصوص الطويلة جداً
                    parts = model_part.split()
                    if parts:
                        report.model = parts[0]
                        report.trim = " ".join(parts[1:]) if len(parts) > 1 else ""
        
        # نوع الهيكل
        body_types = ['SEDAN', 'SUV', 'COUPE', 'TRUCK', 'VAN', 'WAGON', 'CONVERTIBLE', 'HATCHBACK', '4 DR', '2 DR']
        for bt in body_types:
            if bt in html.upper():
                report.body_type = bt
                break
        
        # المحرك
        engine_match = re.search(r'(\d+\.\d+L\s*[A-Z0-9\s]+(?:DOHC|SOHC)?(?:\s*\d+V)?)', html, re.IGNORECASE)
        if engine_match:
            report.engine = engine_match.group(1).strip()
        
        # نوع الوقود
        fuel_types = {'GASOLINE': 'Gasoline', 'DIESEL': 'Diesel', 'ELECTRIC': 'Electric', 'HYBRID': 'Hybrid'}
        for key, val in fuel_types.items():
            if key in html.upper():
                report.fuel_type = val
                break
        
        # نظام الدفع
        drive_match = re.search(r'(ALL WHEEL DRIVE|FRONT WHEEL DRIVE|REAR WHEEL DRIVE|4WD|AWD|FWD|RWD)', html, re.IGNORECASE)
        if drive_match:
            report.drive_type = drive_match.group(1)
        
        # ==========================================
        # 2. ملخص التقرير
        # ==========================================
        
        # استخراج جميع الأسعار (Retail, Wholesale, Trade-In, Private Party)
        self._extract_all_prices(report, html, text)
        
        # عدد الملاك
        owners_match = re.search(r'(\d+)\s*Previous\s*owners?', html, re.IGNORECASE)
        if owners_match:
            report.total_owners = int(owners_match.group(1))
        
        # الحوادث
        if re.search(r'No\s*accidents?\s*(?:or\s*damage\s*)?reported', html, re.IGNORECASE):
            report.accidents_reported = 0
        else:
            accidents_match = re.search(r'(\d+)\s*accidents?\s*reported', html, re.IGNORECASE)
            if accidents_match:
                report.accidents_reported = int(accidents_match.group(1))
        
        # سجلات الخدمة
        service_patterns = [
            r'(\d+)\s*Service\s*(?:history\s*)?records?',
            r'service.*?(\d+)\s*records?',
        ]
        for pattern in service_patterns:
            service_match = re.search(pattern, html, re.IGNORECASE)
            if service_match:
                report.service_records_count = int(service_match.group(1))
                break
        
        # آخر قراءة عداد
        odometer_patterns = [
            r'<strong>([\d,]+)</strong>\s*Last\s*reported\s*odometer',  # HTML format (الأكثر دقة)
            r'>([\d,]+)</strong>\s*Last\s*reported',  # Simpler HTML format
            r'([\d,]+)\s*Last\s*reported\s*odometer',
            r'Last\s*reported\s*odometer\s*reading[:\s]*([\d,]+)',
            r'"lastReportedOdometer"[:\s]*"?([\d,]+)',
            r'lastOdometer[:\s]*"?([\d,]+)',
            r'"text"\s*:\s*"<strong>([\d,]+)</strong>',  # JSON embedded HTML
        ]
        for pattern in odometer_patterns:
            odometer_match = re.search(pattern, html, re.IGNORECASE)
            if odometer_match:
                report.last_odometer = odometer_match.group(1)
                break
        
        # آخر ولاية
        state_match = re.search(r'Last\s*owned\s*in\s*([A-Za-z\s]+?)(?:\d|$)', html, re.IGNORECASE)
        if state_match:
            report.last_state = state_match.group(1).strip()
        
        # ==========================================
        # 3. حالة العنوان (Title History)
        # ==========================================
        
        # حالة العنوان - البحث عن النتيجة الفعلية
        # "Guaranteed No Problem" يعني العنوان نظيف
        if re.search(r'Guaranteed\s*No\s*Problem', html, re.IGNORECASE):
            report.title_status = "Clean"
        elif re.search(r'title.*?clean', html, re.IGNORECASE):
            report.title_status = "Clean"
        elif re.search(r'salvage.*?title|title.*?salvage', html, re.IGNORECASE):
            report.title_status = "Salvage"
        elif re.search(r'rebuilt.*?title|title.*?rebuilt', html, re.IGNORECASE):
            report.title_status = "Rebuilt"
        else:
            # إذا لم يتم الإبلاغ عن مشاكل في العنوان
            if re.search(r'No\s*(?:Issues\s*)?(?:Problem|Reported)', html, re.IGNORECASE):
                report.title_status = "Clean"
            else:
                report.title_status = "Unknown"
        
        # Total Loss
        if re.search(r'No\s*total\s*loss', html, re.IGNORECASE):
            report.total_loss = "No Issues Reported"
        
        # Structural Damage
        if re.search(r'No\s*structural\s*damage', html, re.IGNORECASE):
            report.structural_damage = "No Issues Reported"
        
        # Airbag Deployment
        if re.search(r'No\s*airbag\s*deployment', html, re.IGNORECASE):
            report.airbag_deployment = "No Issues Reported"
        
        # Odometer
        if re.search(r'No\s*indication\s*of\s*(?:an\s*)?odometer\s*rollback', html, re.IGNORECASE):
            report.odometer_status = "No Issues Indicated"
        
        # ==========================================
        # 4. الضمان والاستدعاءات
        # ==========================================
        
        if re.search(r'warranty\s*expired', html, re.IGNORECASE):
            report.basic_warranty = "Expired"
        elif re.search(r'warranty.*active', html, re.IGNORECASE):
            report.basic_warranty = "Active"
        
        if re.search(r'No\s*(?:open\s*)?recalls?\s*reported', html, re.IGNORECASE):
            report.recalls = "No Recalls Reported"
        
        # ==========================================
        # 5. تاريخ الملاك
        # ==========================================
        
        # البحث عن معلومات كل مالك
        for i in range(1, 10):
            owner_pattern = rf'Owner\s*{i}.*?(?:Owner\s*{i+1}|$)'
            owner_match = re.search(owner_pattern, text, re.IGNORECASE | re.DOTALL)
            if owner_match:
                owner_text = owner_match.group(0)
                owner = OwnerHistory(owner_number=i)
                
                # سنة الشراء
                year_match = re.search(r'(?:Year\s*)?purchased[:\s]*(\d{4})', owner_text, re.IGNORECASE)
                if year_match:
                    owner.year_purchased = year_match.group(1)
                
                # نوع المالك
                if 'Personal lease' in owner_text:
                    owner.owner_type = "Personal lease"
                elif 'Personal' in owner_text:
                    owner.owner_type = "Personal"
                elif 'Corporate' in owner_text:
                    owner.owner_type = "Corporate"
                
                # مدة الملكية
                length_match = re.search(r'(\d+\s*(?:years?|yrs?)\.?\s*\d*\s*(?:months?|mo\.?)?)', owner_text, re.IGNORECASE)
                if length_match:
                    owner.length_of_ownership = length_match.group(1)
                
                # الأميال في السنة
                miles_match = re.search(r'([\d,]+)\s*(?:per\s*year|/yr)', owner_text, re.IGNORECASE)
                if miles_match:
                    owner.miles_per_year = miles_match.group(1)
                
                report.owners.append(owner)
        
        # ==========================================
        # 6. السجل التفصيلي
        # ==========================================
        
        # استخراج جميع الأحداث المؤرخة
        date_pattern = r'(\d{2}/\d{2}/\d{4})'
        dates = re.findall(date_pattern, html)
        
        for date in set(dates):
            # البحث عن السياق حول كل تاريخ
            context_pattern = rf'{date}.*?(?=\d{{2}}/\d{{2}}/\d{{4}}|$)'
            context_match = re.search(context_pattern, text, re.DOTALL)
            if context_match:
                context = context_match.group(0)[:500]  # أول 500 حرف
                
                # استخراج المسافة
                mileage_match = re.search(r'([\d,]+)\s*(?:miles?)?', context)
                mileage = mileage_match.group(1) if mileage_match else ""
                
                # الأحداث الشائعة
                events = []
                event_keywords = [
                    'Vehicle serviced', 'Oil and filter changed', 'Title issued',
                    'Registration', 'Inspection', 'Brake', 'Tire', 'Battery',
                    'Sold', 'Offered for sale', 'Certified Pre-Owned'
                ]
                for keyword in event_keywords:
                    if keyword.lower() in context.lower():
                        events.append(keyword)
                
                if events:
                    report.detailed_history.append({
                        "date": date,
                        "mileage": mileage,
                        "events": events
                    })
        
        # إذا لم يتم العثور على عدد سجلات الخدمة، نستخدم عدد الأحداث
        if report.service_records_count == 0 and report.detailed_history:
            report.service_records_count = len(report.detailed_history)
        
        # ==========================================
        # عرض الملخص
        # ==========================================
        
        console.print(f"[green]  ✓ {report.year} {report.make} {report.model} {report.trim}[/green]")
        console.print(f"[dim]    VIN: {report.vin}[/dim]")
        console.print(f"[dim]    الملاك: {report.total_owners}[/dim]")
        console.print(f"[dim]    الحوادث: {report.accidents_reported}[/dim]")
        console.print(f"[dim]    سجلات الخدمة: {report.service_records_count}[/dim]")
        console.print(f"[dim]    آخر قراءة: {report.last_odometer} miles[/dim]")
        console.print(f"[dim]    حالة العنوان: {report.title_status}[/dim]")
        
        return report


async def scrape_full_report(vin: str, output_dir: str = "data/output", get_wholesale: bool = True, fast_mode: bool = False) -> FullCarfaxReport:
    """
    دالة مساعدة لسحب التقرير الكامل وتصديره
    
    Args:
        vin: رقم VIN
        output_dir: مجلد الإخراج
        get_wholesale: هل نحاول الحصول على سعر الـ Wholesale
        fast_mode: وضع سريع (بدون حفظ debug files)
        
    Returns:
        التقرير الكامل
    """
    scraper = FullReportScraper()
    report = await scraper.scrape_report(vin, get_wholesale, fast_mode)
    
    if not report.error:
        # تصدير JSON
        json_path = f"{output_dir}/carfax_full_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report.to_json(json_path)
        
        # تصدير CSV
        import csv
        csv_path = f"{output_dir}/carfax_full_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=report.to_csv_row().keys())
            writer.writeheader()
            writer.writerow(report.to_csv_row())
        
        console.print(f"[green]✓ تم حفظ CSV: {csv_path}[/green]")
    
    return report


# للتشغيل المباشر
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        vin = sys.argv[1]
    else:
        vin = "WBAVC93528K043325"
    
    asyncio.run(scrape_full_report(vin))
