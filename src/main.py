"""
Carfax Vehicle History Scraper - Main CLI
==========================================
Command Line Interface
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional

# Fix Windows console encoding
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Force UTF-8 for Rich console
console = Console(force_terminal=True, legacy_windows=False)

from .config import (
    COOKIES_FILE,
    TOKENS_FILE,
    OUTPUT_DIR,
    get_config_summary,
    validate_credentials
)
from .auth.cookies import CookieManager
from .auth.tokens import TokenManager
from .auth.login import AutoLogin, ensure_authenticated
from .scraper.vehicle_history import (
    VehicleHistoryScraper,
    scrape_single_vin,
    scrape_multiple_vins
)
from .scraper.api_scraper import CarfaxAPIScraper, scrape_with_api
from .export.csv_exporter import CSVExporter


def print_banner():
    """طباعة شعار البرنامج"""
    banner = Text()
    banner.append("╔══════════════════════════════════════════╗\n", style="blue")
    banner.append("║    ", style="blue")
    banner.append("Carfax Vehicle History Scraper", style="bold cyan")
    banner.append("    ║\n", style="blue")
    banner.append("║    ", style="blue")
    banner.append("أداة سحب تقارير تاريخ المركبات", style="dim")
    banner.append("     ║\n", style="blue")
    banner.append("╚══════════════════════════════════════════╝", style="blue")
    console.print(banner)
    console.print()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    أداة لسحب تقارير تاريخ المركبات من Carfax
    
    \b
    الاستخدام:
      python -m src.main scrape --vin "1HGBH41JXMN109186"
      python -m src.main scrape --file vins.txt
      python -m src.main login
      python -m src.main status
    """
    pass


@cli.command()
@click.option("--vin", "-v", help="رقم VIN للمركبة")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="ملف يحتوي أرقام VIN")
@click.option("--output", "-o", help="اسم ملف الإخراج")
@click.option("--append", "-a", is_flag=True, help="إضافة إلى ملف موجود")
@click.option("--api", is_flag=True, help="استخدام API مباشرة (أسرع)")
def scrape(vin: Optional[str], file_path: Optional[str], output: Optional[str], append: bool, api: bool):
    """
    سحب تقارير تاريخ المركبات
    
    \b
    أمثلة:
      python -m src.main scrape --vin "1HGBH41JXMN109186"
      python -m src.main scrape --file vins.txt --output results.csv
    """
    print_banner()
    
    # التحقق من المدخلات
    if not vin and not file_path:
        console.print("[red]✗ يجب تحديد --vin أو --file[/red]")
        sys.exit(1)
    
    # جمع أرقام VIN
    vins = []
    
    if vin:
        vins.append(vin.strip().upper())
        
    if file_path:
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip().upper()
                    if line and len(line) == 17:
                        vins.append(line)
        except Exception as e:
            console.print(f"[red]✗ خطأ في قراءة الملف: {e}[/red]")
            sys.exit(1)
    
    if not vins:
        console.print("[red]✗ لم يتم العثور على أرقام VIN صالحة[/red]")
        sys.exit(1)
    
    console.print(f"[cyan]📋 تم العثور على {len(vins)} رقم VIN[/cyan]")
    
    if api:
        console.print("[green]⚡ وضع API (أسرع)[/green]")
    
    console.print()
    
    # تشغيل الـ Scraper
    asyncio.run(_run_scraper(vins, output, append, api))


async def _run_scraper(vins: list[str], output: Optional[str], append: bool, use_api: bool = False):
    """تشغيل عملية السحب"""
    
    reports = []
    
    # استخدام API إذا كان متاحاً
    if use_api:
        token_manager = TokenManager(TOKENS_FILE)
        
        if not token_manager.load():
            console.print("[red]✗ لم يتم العثور على tokens صالحة[/red]")
            console.print("[yellow]  قم بإضافة tokens.json في مجلد data/[/yellow]")
            return
        
        scraper = CarfaxAPIScraper(token_manager)
        
        async for report in scraper.get_reports(vins):
            if hasattr(report, 'to_dict'):
                reports.append(report.to_dict())
            else:
                reports.append(report)
        
        # تصدير النتائج
        if reports:
            exporter = CSVExporter(OUTPUT_DIR)
            output_file = exporter.export(reports, filename=output, append=append)
            console.print(f"\n[green]✓ تم تصدير {len(reports)} تقرير إلى:[/green]")
            console.print(f"  [blue]{output_file}[/blue]")
        
        return
    
    # الوضع العادي (Playwright)
    # إعداد مدير الـ Cookies
    cookie_manager = CookieManager(COOKIES_FILE)
    
    # التأكد من المصادقة
    if not await ensure_authenticated(cookie_manager):
        console.print("[red]✗ فشل تسجيل الدخول[/red]")
        return
    
    console.print()
    
    # سحب التقارير
    reports = await scrape_multiple_vins(vins, cookie_manager)
    
    console.print()
    
    # عرض الملخص
    exporter = CSVExporter()
    exporter.display_summary(reports)
    
    # تصدير إلى CSV
    if reports:
        console.print()
        exporter.export(reports, output, append)


@cli.command()
def login():
    """
    تسجيل الدخول وحفظ الجلسة
    
    يقوم بتسجيل الدخول باستخدام بيانات الاعتماد في .env
    ويحفظ الـ cookies للاستخدام اللاحق
    """
    print_banner()
    
    if not validate_credentials():
        console.print("[red]✗ بيانات الاعتماد غير موجودة[/red]")
        console.print("[dim]  أضف CARFAX_EMAIL و CARFAX_PASSWORD إلى ملف .env[/dim]")
        sys.exit(1)
    
    asyncio.run(_run_login())


async def _run_login():
    """تنفيذ تسجيل الدخول"""
    cookie_manager = CookieManager(COOKIES_FILE)
    auto_login = AutoLogin(cookie_manager)
    
    success = await auto_login.login()
    
    if success:
        console.print()
        console.print("[green]✓ تم تسجيل الدخول وحفظ الجلسة بنجاح![/green]")
    else:
        console.print()
        console.print("[red]✗ فشل تسجيل الدخول[/red]")
        sys.exit(1)


@cli.command()
def status():
    """
    عرض حالة الجلسة والإعدادات
    """
    print_banner()
    
    # عرض الإعدادات
    config = get_config_summary()
    
    console.print(Panel("[bold]الإعدادات الحالية[/bold]", style="blue"))
    
    for key, value in config.items():
        label = {
            "base_dir": "المجلد الرئيسي",
            "output_dir": "مجلد الإخراج",
            "cookies_file": "ملف الـ Cookies",
            "headless": "وضع Headless",
            "has_credentials": "بيانات الاعتماد",
            "delay_range": "التأخير"
        }.get(key, key)
        
        if key == "has_credentials":
            value = "[green]موجودة[/green]" if value else "[red]غير موجودة[/red]"
        elif key == "headless":
            value = "[green]نعم[/green]" if value else "[yellow]لا[/yellow]"
        
        console.print(f"  {label}: {value}")
    
    console.print()
    
    # التحقق من الجلسة
    console.print(Panel("[bold]حالة الجلسة[/bold]", style="blue"))
    
    cookie_manager = CookieManager(COOKIES_FILE)
    
    if cookie_manager.load():
        console.print(f"  عدد الـ Cookies: {len(cookie_manager)}")
        
        if cookie_manager.is_session_valid():
            console.print("  [green]✓ الجلسة صالحة[/green]")
        else:
            console.print("  [yellow]⚠ الجلسة منتهية[/yellow]")
    else:
        console.print("  [red]✗ لا توجد جلسة محفوظة[/red]")


@cli.command()
def clear():
    """
    مسح الجلسة والـ Cookies
    """
    print_banner()
    
    if click.confirm("هل تريد مسح جميع الـ cookies؟"):
        cookie_manager = CookieManager(COOKIES_FILE)
        cookie_manager.clear()
        
        # حذف الملف
        if COOKIES_FILE.exists():
            COOKIES_FILE.unlink()
            console.print("[green]✓ تم مسح الجلسة[/green]")
        else:
            console.print("[yellow]⚠ لا توجد جلسة للمسح[/yellow]")


def main():
    """نقطة الدخول الرئيسية"""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ تم الإلغاء[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]✗ خطأ غير متوقع: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

