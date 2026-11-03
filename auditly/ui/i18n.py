"""UI translations. Keys are the English strings; missing entries fall back to English."""
from __future__ import annotations

_lang = "en"

AR = {
    # navigation
    "Dashboard": "لوحة التحكم", "Pages": "الصفحات", "Issues": "المشكلات", "Site structure": "هيكل الموقع",
    "AI assistant": "المساعد الذكي", "Compare crawls": "مقارنة الزحف", "Export": "التصدير", "Exports": "التصدير",
    "Integrations": "التكاملات", "History": "السجل", "Settings": "الإعدادات", "Analyse": "التحليل", "Tools": "الأدوات",
    "Workspace": "مساحة العمل",
    # top bar
    "Enter a website URL, e.g. https://example.com": "أدخل رابط الموقع، مثل https://example.com",
    "Start audit": "ابدأ التدقيق", "Pause": "إيقاف مؤقت", "Resume": "استئناف", "Stop": "إيقاف",
    "Crawl settings": "إعدادات الزحف", "Spider (whole site)": "زحف كامل للموقع", "List of URLs": "قائمة روابط",
    "Sitemap only": "خريطة الموقع فقط", "Single URL": "رابط واحد", "Crawled": "تم الزحف", "Queued": "في الانتظار",
    "Speed": "السرعة", "Elapsed": "المدة", "Errors": "أخطاء", "pages/s": "صفحة/ث",
    "Ready. Enter a URL and press Start audit.": "جاهز. أدخل الرابط واضغط ابدأ التدقيق.",
    "Running audits…": "جارٍ تشغيل الفحوصات…", "Audit complete": "اكتمل التدقيق", "Paused": "متوقف مؤقتاً",
    "Stopping…": "جارٍ الإيقاف…",
    # dashboard
    "Health score": "مؤشر الصحة", "Good": "جيد", "Needs work": "يحتاج تحسين", "Poor": "ضعيف", "Technical SEO auditor": "مدقق السيو التقني", "Pages crawled": "الصفحات المفحوصة", "Indexable": "قابلة للفهرسة",
    "Critical": "حرجة", "Warnings": "تحذيرات", "Warning": "تحذير", "Opportunities": "فرص", "Opportunity": "فرصة",
    "Avg response": "متوسط الاستجابة", "Status codes": "رموز الحالة", "Issues by category": "المشكلات حسب الفئة",
    "Top issues": "أهم المشكلات", "Site checks": "فحوصات الموقع", "View all": "عرض الكل",
    "Audit any website": "دقّق أي موقع إلكتروني",
    "Crawl a site to find technical SEO problems, see exactly which URLs are affected and how to fix them.":
        "افحص موقعاً لاكتشاف مشكلات السيو التقنية، ومعرفة الروابط المتأثرة بالضبط وطريقة إصلاحها.",
    "Recent audits": "آخر عمليات التدقيق", "No audits yet.": "لا توجد عمليات تدقيق بعد.", "Open": "فتح",
    "of pages": "من الصفحات", "URLs affected": "رابط متأثر", "Click depth": "عمق النقر",
    # pages
    "Search URLs, titles, H1…": "ابحث في الروابط والعناوين وH1…", "All": "الكل", "Non-indexable": "غير قابلة للفهرسة",
    "With issues": "بها مشكلات", "Columns": "الأعمدة", "Export view": "تصدير العرض", "Select a page to see details.":
        "اختر صفحة لعرض تفاصيلها.", "Inlinks": "روابط داخلة", "Outlinks": "روابط خارجة", "Open in browser": "فتح في المتصفح",
    "Copy URL": "نسخ الرابط", "Details": "التفاصيل",
    # issues
    "Search issues…": "ابحث في المشكلات…", "All categories": "كل الفئات", "Why it matters": "لماذا يهم", "How to fix": "طريقة الإصلاح",
    "Affected URLs": "الروابط المتأثرة", "Copy URLs": "نسخ الروابط", "Export CSV": "تصدير CSV",
    "Select an issue to see the affected URLs and how to fix it.": "اختر مشكلة لعرض الروابط المتأثرة وطريقة إصلاحها.",
    "No issues found": "لا توجد مشكلات", "Detail": "التفاصيل", "Ask AI how to fix": "اسأل الذكاء الاصطناعي",
    # structure
    "URL": "الرابط", "Status": "الحالة", "Title": "العنوان", "Depth": "العمق", "Words": "الكلمات",
    "Path": "المسار", "Count": "العدد", "Pages by click depth": "الصفحات حسب عمق النقر",
    # AI
    "Chat with your crawl": "تحدث مع بيانات الزحف", "Ask anything about this crawl…": "اسأل أي شيء عن هذا الزحف…",
    "Run": "تشغيل", "Save to exports": "حفظ في التصدير", "Copy": "نسخ", "AI output language": "لغة مخرجات الذكاء الاصطناعي",
    "Page URL (for content quality)": "رابط الصفحة (لتحليل جودة المحتوى)", "Thinking…": "جارٍ التفكير…",
    "Add your Anthropic API key in Settings to use AI features.": "أضف مفتاح Anthropic API في الإعدادات لاستخدام ميزات الذكاء الاصطناعي.",
    # compare
    "Before": "قبل", "After": "بعد", "Compare": "قارن", "Fixed": "تم إصلاحها", "New": "جديدة",
    "New URLs": "روابط جديدة", "Removed URLs": "روابط محذوفة",
    # export
    "Choose what to export": "اختر ما تريد تصديره", "Save to": "الحفظ في", "Change folder…": "تغيير المجلد…",
    "Open folder": "فتح المجلد", "Export now": "صدّر الآن", "Exported": "تم التصدير",
    "Exports are saved here by default. You can change the folder at any time.":
        "تُحفظ الملفات هنا افتراضياً، ويمكنك تغيير المجلد في أي وقت.",
    "Ask where to save every time": "اسأل عن مكان الحفظ في كل مرة", "AI prompt language": "لغة موجه الذكاء الاصطناعي",
    # history
    "Saved crawls": "عمليات الزحف المحفوظة", "Delete": "حذف", "Started": "البدء", "Website": "الموقع",
    "interrupted": "متوقف", "complete": "مكتمل", "stopped": "موقوف", "running": "قيد التشغيل",
    # settings
    "Appearance": "المظهر", "Theme": "السمة", "Light": "فاتح", "Dark": "داكن", "Language": "اللغة",
    "AI (Claude)": "الذكاء الاصطناعي (Claude)", "Anthropic API key": "مفتاح Anthropic API", "Model": "النموذج",
    "White-label reports": "تقارير بعلامتك التجارية", "Brand name": "اسم العلامة", "Brand colour": "لون العلامة",
    "Logo file": "ملف الشعار", "Choose…": "اختر…", "Save settings": "حفظ الإعدادات", "Saved": "تم الحفظ",
    "PageSpeed Insights API key (optional)": "مفتاح PageSpeed Insights (اختياري)", "IndexNow key": "مفتاح IndexNow",
    "Crawl profiles": "ملفات إعداد الزحف", "Save profile…": "حفظ ملف…", "Load profile…": "تحميل ملف…",
    # integrations
    "Run on top pages": "تشغيل على أهم الصفحات", "Submit URLs": "إرسال الروابط", "Number of pages": "عدد الصفحات",
    "Strategy": "النوع", "Mobile": "جوال", "Desktop": "سطح المكتب",
    # dialog
    "General": "عام", "Scope": "النطاق", "Rendering & user-agent": "العرض ووكيل المستخدم", "Authentication": "المصادقة",
    "Custom extraction": "استخراج مخصص", "Advanced": "متقدم", "Cancel": "إلغاء", "Apply": "تطبيق", "OK": "موافق",
    "Crawl mode": "وضع الزحف", "Threads": "عدد الطلبات المتوازية", "Delay between requests (s)": "التأخير بين الطلبات (ث)",
    "Max URLs (0 = unlimited)": "أقصى عدد روابط (0 = بلا حد)", "Max depth (0 = unlimited)": "أقصى عمق (0 = بلا حد)",
    "Respect robots.txt": "احترام robots.txt", "Use XML sitemaps": "استخدام خرائط XML", "Crawl subdomains": "زحف النطاقات الفرعية",
    "Check external links": "فحص الروابط الخارجية", "Check images (broken / size)": "فحص الصور (معطلة / الحجم)",
    "Render JavaScript (Playwright)": "تنفيذ JavaScript (Playwright)", "Compare mobile vs desktop content": "مقارنة محتوى الجوال وسطح المكتب",
    "User-agent": "وكيل المستخدم", "Include only URLs matching (regex, one per line)": "تضمين الروابط المطابقة فقط (regex، واحد بكل سطر)",
    "Exclude URLs matching (regex, one per line)": "استبعاد الروابط المطابقة (regex، واحد بكل سطر)",
    "Remove URL parameters (comma separated)": "إزالة معاملات الرابط (مفصولة بفواصل)", "Username": "اسم المستخدم",
    "Password": "كلمة المرور", "Cookies": "ملفات تعريف الارتباط", "Extra headers (Name: value per line)": "ترويسات إضافية (اسم: قيمة بكل سطر)",
    "Timeout (s)": "المهلة (ث)", "Retries": "إعادة المحاولة", "Verify TLS certificates": "التحقق من شهادات TLS",
    "URLs (one per line)": "الروابط (واحد بكل سطر)", "Sitemap URL (blank = auto-detect)": "رابط خريطة الموقع (فارغ = اكتشاف تلقائي)",
    "Add rule": "إضافة قاعدة", "Remove": "إزالة", "Name": "الاسم", "Type": "النوع", "Expression": "التعبير", "Attribute": "الخاصية",
    # severities / categories
    "critical": "حرجة", "warning": "تحذير", "opportunity": "فرصة",
    "Response codes": "رموز الاستجابة", "Page titles": "عناوين الصفحات", "Meta descriptions": "أوصاف الميتا",
    "Headings": "العناوين الرئيسية", "Canonicals": "الروابط الأساسية", "Content": "المحتوى", "Images": "الصور",
    "Links": "الروابط", "Security": "الأمان", "URL structure": "بنية الروابط", "Hreflang": "Hreflang",
    "Structured data": "البيانات المنظمة", "Performance": "الأداء", "Pagination": "ترقيم الصفحات",
    "Sitemaps & robots.txt": "خرائط الموقع وrobots.txt", "AI / GEO readiness": "الجاهزية للذكاء الاصطناعي (GEO)",
}


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in ("en", "ar") else "en"


def language() -> str:
    return _lang


def is_rtl() -> bool:
    return _lang == "ar"


def t(text: str) -> str:
    if _lang == "ar":
        return AR.get(text, text)
    return text
