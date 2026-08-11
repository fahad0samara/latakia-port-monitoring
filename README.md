# 🛰️ رصد وتحليل النشاط البحري — مرفأ اللاذقية (Satellite-Based Port Activity Monitoring)

نظام كامل يحمّل صور أقمار صناعية **حقيقية** (Copernicus Sentinel-1 SAR و Sentinel-2 البصري)،
يكتشف السفن داخل **الحدود الجغرافية الحقيقية لمرفأ اللاذقية** (سوريا)، يبني سلسلة زمنية 2022–الآن،
ويحلل تغيّر النشاط شهريًا وسنويًا — **بدون أي أرقام افتراضية**، مع "No data available" حيث لا توجد صور.

---

## 🚀 التشغيل السريع

```bash
# 1) تثبيت الحزم
pip install -r requirements.txt

# 2) (اختياري) إعادة البناء الكامل من الصفر — يجلب كل الصور ويعالجها:
python3 -m src.pipeline --s1 --s2          # تحميل + كشف (قابل للاستئناف)

# 3) التحليل والرسوم والخرائط:
python3 -m src.analysis                     # dataset شهري/سنوي + اختبارات الاتجاه
python3 -m src.charts                       # مخططات Plotly (HTML+PNG)
python3 -m src.maps                         # خريطة Folium + خريطة الكثافة
python3 -m src.validation                   # التحقق المتبادل S1↔S2
python3 -m src.anomaly                      # كشف الشذوذ الإحصائي (EWMA/CUSUM)
python3 -m src.tracking                     # بناء مسارات السفن الفريدة
python3 -m src.insights                     # مدة البقاء + ضغط التشغيل
python3 -m src.compare                      # مقارنة اللاذقية · طرطوس · بانياس
python3 -m src.ais_verify                   # تحقق AIS (مطابقة + تقدير أنواع)
python3 -m src.geotiff                      # طبقات GeoTIFF على الشبكة الثابتة
python3 -m src.exporter                     # تصدير GeoJSON + Summary

# 4) لوحة المعلومات:
streamlit run src/dashboard.py
```

> ⚠️ **لا تشغّل `src/fix_data.py` بعد المعالجة** — أدى سابقًا إلى دمج مفرط لأجزاء السفن؛
> حلّت محله المواءمة التلقائية لعدادات المشاهدات داخل `analysis.load_scenes()`.

> **ملاحظة:** مستودع المشروع يأتي مع بيانات معالجة مسبقًا في `data/detections/`؛
> التشغيل أعلاه يحدّثها فقط (السكربتات قابلة للاستئناف وتتخطى المشاهد المنجزة).

**تحديث البيانات (يدوي أو عبر cron — انظر «الأتمتة» أدناه):**
```bash
python3 update_data.py --to 2026-12-31     # تمديد النطاق الزمني
python3 update_data.py --full              # تحديث + إعادة توليد التقارير والتصدير كاملًا
python3 update_data.py --ais <aishub-user> --full   # جلب AIS حي ثم تحديث كامل
```

---

## 🤖 الأتمتة — التحديث الأسبوعي التلقائي

```bash
bash scripts/install_cron.sh               # تثبيت جدولة أسبوعية (الأحد 02:30، قابلة للتغيير)
bash scripts/install_cron.sh --remove      # إزالتها
bash scripts/run_weekly_update.sh          # تشغيل يدوي كامل (نفس ما يفعله cron)
```

ماذا يحدث كل تشغيل (كل خطوة مسجلة في `logs/update_weekly.log` ولا يوقف فشلُها البقية):
1. استعلام STAC عن مشاهدات Sentinel-1/Sentinel-2 الجديدة منذ آخر تشغيل.
2. معالجة المشاهدات الجديدة فقط (قابل للاستئناف).
3. إعادة حساب التحليلات والمخططات والمؤشرات.
4. إعادة توليد التقارير الأربعة: HTML / DOCX / XLSX / PDF (PDF عبر Chromium headless).
5. تحديث كل التصدير: GeoJSON، Summary، مسارات السفن، الشذوذ، طبقات GeoTIFF، ملف AIS.
6. حماية تداخل: لا يعمل تشغيلان معًا (قفل). على Windows: Task Scheduler.

---

## 🗂️ بنية المشروع

```
latakia-port-monitoring/
├── config/
│   ├── latakia_osm.geojson      # حدود المرفأ الحقيقية (OSM way 722818042) + الساحل + الكاسر
│   ├── zones.geojson            # مناطق الدراسة (مرفأ <400م / مرسى 0.4-4كم)
│   ├── ne_10m_land.geojson      # اليابسة (Natural Earth 10m)
│   ├── masks.npz / fixed_grid.json  # أقنعة محسوبة (شبكة UTM 36N ثابتة 10م)
│   └── stac_cache/              # كتالوج المشاهد المختارة (Sentinel-1/2)
├── src/
│   ├── config.py                # الإعدادات ومنطقة الدراسة
│   ├── boundaries.py            # الحدود الحقيقية + الأقنعة + قناع SAR المحسّن
│   ├── stac.py                  # البحث في Planetary Computer STAC واختيار المشاهد
│   ├── detect.py                # كشف السفن SAR (Lee + CFAR + VV/VH + watershed)
│   ├── pipeline.py              # المعالجة المجمّعة (S1 كشف / S2 تحقق بصري)
│   ├── analysis.py              # السلسلة الزمنية + مؤشر النشاط + Mann-Kendall + Regimes
│   ├── charts.py                # مخططات Plotly
│   ├── maps.py / map_fig.py     # خريطة Folium + خريطة كثافة + خريطة تفاعلية مدمجة
│   ├── validation.py            # تحقق متبادل S1↔S2 + مؤشرات جودة
│   ├── anomaly.py               # كشف الشذوذ (EWMA + CUSUM)
│   ├── tracking.py              # تتبع السفن عبر الزمن (مسارات فريدة)
│   ├── insights.py              # مدة البقاء + ضغط التشغيل (سقف القدرة)
│   ├── compare.py               # المقارنة الإقليمية: اللاذقية · طرطوس · بانياس
│   ├── ais_verify.py            # تحقق AIS (مطابقة حقيقية + تقدير أنواع من الأبعاد)
│   ├── geotiff.py               # تصدير طبقات GeoTIFF (العد/السنوي/الإشغال/المشهد)
│   ├── exporter.py              # تصدير GeoJSON + Summary JSON (لـ GIS)
│   ├── build_dataset.py         # بناء الـDataset النهائي (مشاهدات + سفن)
│   └── dashboard.py             # Streamlit Dashboard (14 تبويبًا)
├── scripts/
│   ├── install_cron.sh          # تثبيت/إزالة الجدولة الأسبوعية
│   ├── run_weekly_update.sh     # مشغل cron (قفل + تسجيل)
│   └── make_contact_sheets.py   # دمج مقاطع السفن في لوحات اتصال (ضغط الأرشفة)
├── data/
│   ├── raw_s1/<scene>/          # صورة المشهد، overlay الكشف، vessels.json، لوحة مقاطع sheet.jpg
│   ├── raw_s2/<scene>/rgb.png   # صور بصرية S2 للمقارنة
│   ├── ais/                     # رسائل AIS الحقيقية (jsonl/csv) — التنسيق في README.md داخله
│   ├── geotiff/                 # طبقات GeoTIFF المُصدَّرة
│   ├── tartus/                  # سلسلة مرفأ طرطوس (للمقارنة الإقليمية)
│   ├── baniyas/                 # سلسلة مرفأ بانياس النفطي (للمقارنة الإقليمية)
│   └── detections/              # s1_scenes.jsonl, monthly.csv, yearly.csv, summary.json,
│                                # tracks.csv, anomalies.json, ais_report.json, vessels.geojson, …
├── outputs/charts|maps/         # المخططات والخرائط (HTML + PNG)
├── logs/                        # سجلات التحديث (يدوي + أسبوعي)
├── docs/                        # التقارير النهائية (HTML/PDF/DOCX/XLSX)
└── update_data.py               # محرك التحديث (يدعم --full و --ais و --offline)
```

---

## 📡 مصادر البيانات (كلها حقيقية ومفتوحة)

| المصدر | البيانات | الوصول |
|---|---|---|
| **Copernicus Sentinel-1 RTC** (ESA) | رادار 10م VV+VH — لا يتأثر بالغيوم/الليل | Microsoft Planetary Computer (STAC مفتوح، مجاني) |
| **Copernicus Sentinel-2 L2A** (ESA) | بصري 10م (RGB) — للتحقق البصري | Microsoft Planetary Computer |
| **OpenStreetMap** | مضلع «مرفأ اللاذقية» (way 722818042)، كاسر الأمواج، خط الساحل | Overpass API |
| **Natural Earth 10m** | اليابسة المرجعية | تحميل مفتوح |
| **OpenStreetMap** (بانياس) | حوض مرفأ بانياس النفطي: كاسر أمواج OSM 1340825778 (حلقة مغلقة) | Overpass API |
| **AIS (اختياري)** | هويات السفن وأنواعها (Cargo/Tanker/Container) | ملفات محلية أو AISHub (مجاني) |

كل مشهد يُسجَّل بـ: معرّفه الرسمي، تاريخ ووقت الالتقاط، مداره، وتغطيته — أي أن كل رقم في
التقرير قابل للتتبع إلى صورة قمر صناعي حقيقية (تُعرض في عارض الصور داخل الـ Dashboard).

---

## 🛰️ التحقق AIS — هويات السفن وأنواعها

مستويان منفصلان بوضوح في تبويب «التحقق AIS»:

1. **مطابقة AIS حقيقية** — ضع رسائل AIS في `data/ais/` (JSONL أو CSV؛ الأعمدة موثقة في
   `data/ais/README.md`) بتنسيق: `timestamp, lon, lat, mmsi, imo, name, ship_type, length_m,
   width_m, sog, cog, destination`. تُربط كل سفينة مكتشفة بأقرب رسالة (≤ 600م و≤ 45 دقيقة)
   وتُعرض هويتها الفعلية. الجلب المباشر من AISHub (مجاني ~1,000 رسالة/يوم):
   `python3 -m src.ais_verify --aishub <username>`.
2. **تقدير من الأبعاد** — تصنيف تقريبي من طول السفينة في الرادار فقط (عرض SAR مضخّم 1.5–2×
   بسبب انبثاق الرادار فلا يُستخدم)، مُعلَّم دائمًا كتقدير وليس هوية مؤكدة. لا يُظهر أبدًا
   كهوية AIS حقيقية.

المخرجات: `data/detections/ais_matches.csv` (المطابقات)، `type_profile.csv` (التركيب الشهري)،
`ais_report.json` (ملخص آلي).

---

## 🗺️ تصدير GeoTIFF — طبقات راستر لبرامج GIS

تُبنى كل الطبقات على **نفس شبكة UTM-36N الثابتة (10م)** المستخدمة في خط الكشف
(`config/fixed_grid.json`) فتنطبق بكسلًا-بكسل على صور SAR والأقنعة. كل القيم عدّادات حقيقية من
ملفات `vessels.json` — مجموع خلايا طبقة العد يساوي إجمالي سجلات السفن (6,678 حاليًا) تمامًا.
خلايا اليابسة الخالية = NoData (وسفن الأرصفة على خلايا اليابسة تبقى بقيمها الحقيقية).

| الطبقة | المحتوى |
|---|---|
| `vessel_count_total.tif` (+`_4326`) | إجمالي الاكتشافات لكل خلية 10م |
| `vessel_count_by_year.tif` (+`_4326`) | مكدس متعدد النطاقات: نطاق لكل سنة |
| `occupancy_share.tif` (+`_4326`) | حصة الإشغال (اكتشافات ÷ عدد المشاهدات الصالحة) |
| `scene_<id>.tif` | خريطة حضور 0/1 لمشهد واحد |

التوليد: `python3 -m src.geotiff --latest` أو من الواجهة (قسم «تصدير GeoTIFF» في تبويب
بيانات المشاهدات، مع زر ZIP لكل الطبقات).

---

## 🔬 منهجية كشف السفن (Sentinel-1 SAR)

1. قراءة النطاق الجزئي (COG subset) لمنطقة الدراسة من كل مشهد.
2. إسقاط على شبكة UTM-36N ثابتة بدقة 10م (تطابق بكسل كامل بين المشاهد).
3. قناع اليابسة = Natural Earth + مضلع المرفأ OSM + الكاسر + **قناع مشتق من متوسط 30 مشهد SAR** (متحقق بالارتباط مع اليابسة المرجعية).
4. فلتر Lee (5×5) لتنعيم التشويش (speckle) مع الحفاظ على الأهداف النقطية.
5. عتبة تكيفية على مياه مفتوحة: `T = μ + k·σ` (VV)، وتحقق متقاطع VH.
6. مكونات متصلة + فك التحام السفن المتلاصقة عند الأرصفة (watershed بمؤشرات القمم).
7. لكل سفينة: إحداثيات WGS84، الطول/العرض، ذروة الاستطاعة (dB)، نسبة VH، المسافة من المرفأ، المنطقة (داخل المرفأ/مرسى/عبور).
8. النوع: **تقديري من الأبعاد** فقط — التصنيف المؤكد (Cargo/Tanker/Container) يتطلب مطابقة AIS (انظر أعلاه).

**مؤشر النشاط:** متوسط السفن لكل مشاهدة (بعد تصحيح التغطية الجزئية) — لذلك لا يختلط حجم العينة
بمستوى النشاط، ويُحسب فقط للأشهر التي لديها ≥ 1 مشاهدة.

---

## 📊 المخرجات

- **Dataset زمني** (`data/detections/`): لكل مشاهدة — acquisition date/time, satellite, orbit,
  vessel_count (مكونات + تقدير مفكك), vessel_location (GeoJSON points), port_area, activity metrics.
- **تحليل شهري/سنوي**: متوسط النشاط، أعلى/أدنى شهر، YoY%، MoM%، اختبار Mann-Kendall،
  مقارنة الفترات (قبل/بعد كانون الأول 2024، سنة-لسنة) مع p-value وفاصل ثقة.
- **خرائط**: Folium تفاعلية (حدود حقيقية + نقاط + كثافة) وخريطة كثافة ثابتة على خلفية SAR حقيقية.
- **لوحة معلومات** Streamlit: KPIs + مخططات تفاعلية + خريطة + عارض صور + تحقق + **تحقق AIS** + **أتمتة**.
- **تقارير**: `docs/FINAL_REPORT.html|pdf|docx|xlsx`، `docs/PBI_REPORT.html|pdf`، `docs/EXEC_BRIEF.html|pdf`.
- **تصدير GIS**: GeoJSON (نقاط WGS84)، طبقات GeoTIFF (UTM-36N وWGS84)، مكدس سنوي.
- **أرشفة مضغوطة**: مقاطع السفن مدمجة في لوحة اتصال واحدة لكل مشهد (`vessels/sheet.jpg`)
  للحفاظ على حجم المشروع ضمن حدود التخزين — البيانات الرقمية في vessels.json لم تُمَس.

## ⚠️ حدود المنهجية (باختصار)

- دقة 10م: السفن < ~15-20م غالبًا غير مكتشفة (قوارب الصيد الصغيرة).
- السفن المتلاصقة على الرصيف تُفكّ تقديريًا (يُعرض كلا الرقمين: مكونات وتقدير).
- تصنيف النوع من الأبعاد تقديري؛ الهوية المؤكدة تتطلب مطابقة AIS.
- حالة البحر العالية قد تخفي سفنًا صغيرة في المرسى.
- التحقق البصري S2 مقيد بالغيوم.

## 📄 الترخيص والبيانات

- صور Sentinel-1/2: ESA/Copernicus — بيانات مفتوحة (CC BY-SA 3.0 IGO للإسناد).
- OpenStreetMap: © مساهمو OpenStreetMap (ODbL).
- Natural Earth: ملكية عامة.
- كود المشروع: حر للاستخدام مع الإشارة إلى المصدر.
