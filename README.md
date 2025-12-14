# Carfax Vehicle History Scraper

أداة Python لسحب تقارير تاريخ المركبات من Carfax باستخدام **Crawl4AI**.

## المميزات

- ✅ سحب تقارير تاريخ المركبات باستخدام VIN
- ✅ تسجيل دخول تلقائي عند انتهاء الجلسة
- ✅ حفظ واستعادة الـ cookies
- ✅ تصدير البيانات إلى CSV
- ✅ واجهة سطر أوامر سهلة الاستخدام
- ✅ تأخير عشوائي لتجنب الحظر

## التثبيت

### 1. إنشاء بيئة افتراضية

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. تثبيت المتطلبات

```bash
pip install -r requirements.txt
```

### 3. تثبيت Playwright

```bash
playwright install chromium
```

### 4. إعداد ملف البيئة

انسخ ملف `env.example.txt` إلى `.env`:

```bash
copy env.example.txt .env
```

ثم أضف بيانات الاعتماد:

```env
CARFAX_EMAIL=your_email@example.com
CARFAX_PASSWORD=your_password
```

## الاستخدام

### عرض المساعدة

```bash
python -m src.main --help
```

### سحب تقرير مركبة واحدة

```bash
python -m src.main scrape --vin "1HGBH41JXMN109186"
```

### سحب عدة مركبات من ملف

أنشئ ملف `vins.txt` يحتوي رقم VIN في كل سطر:

```
1HGBH41JXMN109186
2HGFC2F59MH505012
3GNDA13D36S573217
```

ثم شغّل:

```bash
python -m src.main scrape --file vins.txt --output results.csv
```

### تسجيل الدخول يدوياً

```bash
python -m src.main login
```

### عرض حالة الجلسة

```bash
python -m src.main status
```

### مسح الجلسة

```bash
python -m src.main clear
```

## البيانات المستخرجة

| الحقل | الوصف |
|-------|-------|
| VIN | رقم تعريف المركبة |
| Year | سنة الصنع |
| Make | الشركة المصنعة |
| Model | الموديل |
| Trim | الفئة |
| Owners | عدد الملاك السابقين |
| Accidents | عدد الحوادث المسجلة |
| Service Records | عدد سجلات الخدمة |
| Mileage | قراءة عداد المسافات |
| Title Status | حالة العنوان (Clean/Salvage/etc) |

## هيكل المشروع

```
carfax1/
├── src/
│   ├── __init__.py
│   ├── main.py              # واجهة سطر الأوامر
│   ├── config.py            # الإعدادات
│   ├── auth/
│   │   ├── cookies.py       # إدارة الـ cookies
│   │   └── login.py         # تسجيل الدخول التلقائي
│   ├── scraper/
│   │   └── vehicle_history.py  # سحب التقارير
│   └── export/
│       └── csv_exporter.py  # تصدير CSV
├── data/
│   ├── cookies.txt          # ملف الـ cookies (يُنشأ تلقائياً)
│   └── output/              # ملفات الإخراج
├── requirements.txt
├── .env                     # بيانات الاعتماد (لا تشاركه!)
└── README.md
```

## الأمان

⚠️ **تحذيرات مهمة:**

1. **لا تشارك ملف `.env`** - يحتوي بيانات الدخول
2. **لا تشارك ملف `cookies.txt`** - يحتوي جلسة المصادقة
3. كلا الملفين مُضافان إلى `.gitignore`

## استكشاف الأخطاء

### "الجلسة منتهية"

```bash
python -m src.main login
```

### "بيانات الاعتماد غير موجودة"

تأكد من وجود ملف `.env` مع المتغيرات الصحيحة.

### "VIN غير صالح"

- VIN يجب أن يكون 17 حرفاً
- لا يحتوي على الأحرف I, O, Q

## المتطلبات

- Python 3.10+
- Playwright (Chromium)
- اتصال إنترنت

## الترخيص

للاستخدام الشخصي فقط. يرجى احترام شروط خدمة Carfax.

