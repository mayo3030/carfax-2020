"""
API Scraper Module
==================
سحب تقارير المركبات باستخدام API مباشرة (أسرع من المتصفح)
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, AsyncGenerator
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from ..auth.tokens import TokenManager
from ..config import MIN_DELAY, MAX_DELAY, PROXY_ENABLED, get_httpx_proxy

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
    damage_reported: bool = False
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
            "damage_reported": self.damage_reported,
            "service_records": self.service_records,
            "mileage": self.mileage,
            "title_status": self.title_status,
            "report_date": self.report_date,
            "error": self.error
        }


class CarfaxAPIScraper:
    """
    سحب تقارير المركبات باستخدام Carfax API
    
    أسرع وأكثر موثوقية من scraping عبر المتصفح
    """
    
    # API Base URL - Carfax Dealer API (من JWT audience)
    BASE_URL = "https://dealers.carfax.com"
    
    # Endpoints
    VHR_ENDPOINT = "/api/vhr"
    VEHICLE_SEARCH_ENDPOINT = "/api/vehicle"
    
    def __init__(self, token_manager: TokenManager):
        """
        تهيئة الـ API Scraper
        
        Args:
            token_manager: مدير الـ tokens
        """
        self.token_manager = token_manager
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """الحصول على HTTP client مع دعم البروكسي"""
        if self._client is None or self._client.is_closed:
            # إعداد البروكسي إذا كان مفعل
            proxy_url = get_httpx_proxy()
            
            # تعطيل التحقق من SSL عند استخدام البروكسي (Bright Data يستخدم self-signed cert)
            self._client = httpx.AsyncClient(
                timeout=30.0,
                proxy=proxy_url,
                verify=not PROXY_ENABLED,  # تعطيل SSL verification مع البروكسي
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Origin": "https://www.carfaxonline.com",
                    "Referer": "https://www.carfaxonline.com/"
                }
            )
            
            if PROXY_ENABLED:
                console.print("[cyan]  🌐 API: البروكسي مفعل[/cyan]")
        
        return self._client
    
    async def close(self):
        """إغلاق الـ client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def get_report(self, vin: str) -> VehicleReport:
        """
        سحب تقرير مركبة واحدة
        
        Args:
            vin: رقم VIN
            
        Returns:
            تقرير المركبة
        """
        # التحقق من صحة VIN
        if not self._validate_vin(vin):
            return VehicleReport(vin=vin, error="VIN غير صالح")
        
        # التحقق من الـ token
        if not self.token_manager.is_valid:
            return VehicleReport(vin=vin, error="Token غير صالح أو منتهي")
        
        console.print(f"[blue]🔍 API: جاري سحب تقرير: {vin}[/blue]")
        
        try:
            client = await self._get_client()
            headers = self.token_manager.get_auth_header()
            
            # طلب التقرير - نجرب GET أولاً
            response = await client.get(
                f"{self.BASE_URL}{self.VHR_ENDPOINT}/{vin}",
                headers=headers
            )
            
            # إذا فشل GET، نجرب POST
            if response.status_code == 404 or response.status_code == 405:
                response = await client.post(
                    f"{self.BASE_URL}{self.VHR_ENDPOINT}",
                    headers=headers,
                    json={"vin": vin}
                )
            
            if response.status_code == 401:
                return VehicleReport(vin=vin, error="Token منتهي - يرجى تجديده")
            
            if response.status_code == 404:
                return VehicleReport(vin=vin, error="VIN غير موجود")
            
            # طباعة معلومات الاستجابة للتصحيح
            console.print(f"[dim]  Status: {response.status_code}[/dim]")
            
            if response.status_code != 200:
                console.print(f"[dim]  Response: {response.text[:200]}...[/dim]")
                return VehicleReport(
                    vin=vin, 
                    error=f"خطأ API: {response.status_code}"
                )
            
            # التحقق من أن الاستجابة JSON
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                console.print(f"[yellow]  ⚠ Content-Type: {content_type}[/yellow]")
                console.print(f"[dim]  Response: {response.text[:300]}...[/dim]")
                return VehicleReport(vin=vin, error="الاستجابة ليست JSON")
            
            data = response.json()
            
            # استخراج البيانات
            report = self._parse_report(vin, data)
            
            # تأخير عشوائي
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            
            return report
            
        except httpx.TimeoutException:
            return VehicleReport(vin=vin, error="انتهت مهلة الاتصال")
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
            task = progress.add_task(f"[cyan]سحب {total} تقرير (API)...", total=total)
            
            for i, vin in enumerate(vins):
                report = await self.get_report(vin)
                
                progress.update(task, advance=1)
                
                if progress_callback:
                    progress_callback(i + 1, total, report)
                
                yield report
        
        await self.close()
    
    def _validate_vin(self, vin: str) -> bool:
        """التحقق من صحة VIN"""
        if not vin:
            return False
        
        vin = vin.strip().upper()
        if len(vin) != 17:
            return False
        
        if any(c in vin for c in "IOQ"):
            return False
        
        return True
    
    def _parse_report(self, vin: str, data: dict) -> VehicleReport:
        """
        تحليل بيانات التقرير من API
        
        Args:
            vin: رقم VIN
            data: بيانات API
            
        Returns:
            تقرير المركبة
        """
        report = VehicleReport(vin=vin, raw_data=data)
        
        try:
            # استخراج معلومات المركبة
            vehicle = data.get("vehicle", {})
            report.year = str(vehicle.get("year", ""))
            report.make = vehicle.get("make", "")
            report.model = vehicle.get("model", "")
            report.trim = vehicle.get("trim", "")
            
            # استخراج الإحصائيات
            summary = data.get("summary", {})
            report.owners = summary.get("ownerCount")
            report.accidents = summary.get("accidentCount", 0)
            report.damage_reported = summary.get("damageReported", False)
            report.service_records = summary.get("serviceRecordCount")
            
            # استخراج المسافة
            odometer = data.get("odometer", {})
            if odometer:
                report.mileage = str(odometer.get("lastReading", ""))
            
            # استخراج حالة العنوان
            title = data.get("title", {})
            if title:
                report.title_status = title.get("status", "")
            
            if report.year and report.make:
                console.print(
                    f"[green]  ✓ {report.year} {report.make} {report.model} | "
                    f"Owners: {report.owners} | Accidents: {report.accidents}[/green]"
                )
            
        except Exception as e:
            report.error = f"خطأ في التحليل: {e}"
            console.print(f"[red]  ✗ خطأ في التحليل: {e}[/red]")
        
        return report


async def scrape_with_api(
    vins: list[str],
    token_manager: TokenManager
) -> list[VehicleReport]:
    """
    دالة مساعدة للسحب باستخدام API
    
    Args:
        vins: قائمة أرقام VIN
        token_manager: مدير الـ tokens
        
    Returns:
        قائمة التقارير
    """
    scraper = CarfaxAPIScraper(token_manager)
    reports = []
    
    async for report in scraper.get_reports(vins):
        reports.append(report)
    
    return reports

