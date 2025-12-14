"""
CSV Exporter Module
===================
تصدير البيانات إلى ملفات CSV
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from ..scraper.vehicle_history import VehicleReport
from ..config import OUTPUT_DIR

console = Console()


class CSVExporter:
    """
    تصدير تقارير المركبات إلى ملفات CSV
    
    يدعم:
    - تصدير تقرير واحد أو متعددة
    - إضافة إلى ملف موجود
    - إنشاء ملف جديد بختم زمني
    """
    
    # الأعمدة الافتراضية
    DEFAULT_COLUMNS = [
        "vin",
        "year",
        "make",
        "model",
        "trim",
        "owners",
        "accidents",
        "service_records",
        "mileage",
        "title_status",
        "report_date",
        "error"
    ]
    
    # أسماء الأعمدة بالعربية (اختياري)
    ARABIC_COLUMNS = {
        "vin": "رقم VIN",
        "year": "السنة",
        "make": "الشركة المصنعة",
        "model": "الموديل",
        "trim": "الفئة",
        "owners": "عدد الملاك",
        "accidents": "عدد الحوادث",
        "service_records": "سجلات الخدمة",
        "mileage": "المسافة",
        "title_status": "حالة العنوان",
        "report_date": "تاريخ التقرير",
        "error": "خطأ"
    }
    
    def __init__(
        self, 
        output_dir: Optional[Path] = None,
        use_arabic_headers: bool = False
    ):
        """
        تهيئة المُصدّر
        
        Args:
            output_dir: مجلد الإخراج
            use_arabic_headers: استخدام عناوين عربية
        """
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_arabic_headers = use_arabic_headers
        
    def export(
        self, 
        reports: list[VehicleReport],
        filename: Optional[str] = None,
        append: bool = False
    ) -> Path:
        """
        تصدير التقارير إلى CSV
        
        Args:
            reports: قائمة التقارير
            filename: اسم الملف (اختياري)
            append: إضافة إلى ملف موجود
            
        Returns:
            مسار الملف المُنشأ
        """
        if not reports:
            console.print("[yellow]⚠ لا توجد تقارير للتصدير[/yellow]")
            return None
            
        # تحديد اسم الملف
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"carfax_reports_{timestamp}.csv"
        
        # التأكد من امتداد .csv
        if not filename.endswith(".csv"):
            filename += ".csv"
            
        output_path = self.output_dir / filename
        
        # تحويل التقارير إلى قائمة قواميس
        data = [report.to_dict() for report in reports]
        
        # إنشاء DataFrame
        df = pd.DataFrame(data, columns=self.DEFAULT_COLUMNS)
        
        # تغيير العناوين للعربية إذا مطلوب
        if self.use_arabic_headers:
            df.columns = [self.ARABIC_COLUMNS.get(col, col) for col in df.columns]
        
        # الكتابة للملف
        mode = "a" if append and output_path.exists() else "w"
        header = not (append and output_path.exists())
        
        df.to_csv(
            output_path,
            mode=mode,
            header=header,
            index=False,
            encoding="utf-8-sig"  # للدعم الأفضل في Excel
        )
        
        console.print(f"[green]✓ تم تصدير {len(reports)} تقرير إلى:[/green]")
        console.print(f"  [blue]{output_path}[/blue]")
        
        return output_path
    
    def export_single(
        self, 
        report: VehicleReport,
        filename: Optional[str] = None
    ) -> Path:
        """
        تصدير تقرير واحد
        
        Args:
            report: التقرير
            filename: اسم الملف
            
        Returns:
            مسار الملف
        """
        return self.export([report], filename)
    
    def append_to_file(
        self, 
        reports: list[VehicleReport],
        filename: str
    ) -> Path:
        """
        إضافة تقارير إلى ملف موجود
        
        Args:
            reports: التقارير الجديدة
            filename: اسم الملف
            
        Returns:
            مسار الملف
        """
        return self.export(reports, filename, append=True)
    
    def display_summary(self, reports: list[VehicleReport]) -> None:
        """
        عرض ملخص التقارير في الـ console
        
        Args:
            reports: قائمة التقارير
        """
        if not reports:
            console.print("[yellow]لا توجد تقارير[/yellow]")
            return
            
        # إنشاء جدول
        table = Table(title="ملخص التقارير")
        
        # إضافة الأعمدة
        table.add_column("VIN", style="cyan")
        table.add_column("المركبة", style="green")
        table.add_column("الملاك", justify="center")
        table.add_column("الحوادث", justify="center")
        table.add_column("الحالة", style="yellow")
        
        # إضافة الصفوف
        for report in reports:
            vehicle = f"{report.year or '?'} {report.make or '?'} {report.model or '?'}"
            owners = str(report.owners) if report.owners is not None else "-"
            accidents = str(report.accidents) if report.accidents is not None else "-"
            
            if report.error:
                status = f"[red]✗ {report.error[:20]}...[/red]"
            else:
                status = "[green]✓ نجاح[/green]"
            
            table.add_row(
                report.vin,
                vehicle,
                owners,
                accidents,
                status
            )
        
        console.print(table)
        
        # إحصائيات
        success_count = sum(1 for r in reports if not r.error)
        error_count = sum(1 for r in reports if r.error)
        
        console.print(f"\n[bold]الإجمالي:[/bold] {len(reports)} تقرير")
        console.print(f"  [green]✓ نجاح: {success_count}[/green]")
        console.print(f"  [red]✗ فشل: {error_count}[/red]")


def quick_export(
    reports: list[VehicleReport],
    filename: Optional[str] = None
) -> Path:
    """
    دالة مساعدة للتصدير السريع
    
    Args:
        reports: قائمة التقارير
        filename: اسم الملف (اختياري)
        
    Returns:
        مسار الملف
    """
    exporter = CSVExporter()
    return exporter.export(reports, filename)

