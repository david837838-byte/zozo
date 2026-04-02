# نشر التطبيق على PythonAnywhere
# Deploying to PythonAnywhere

## الخطوات:

### 1. إنشاء حساب على PythonAnywhere
- زُر الموقع: https://www.pythonanywhere.com
- اضغط على "Sign up"
- أكمل البيانات واختر خطة (يوجد خطة مجانية)

### 2. بعد تسجيل الدخول:

#### الطريقة الأولى: استخدام Git (الأسهل)

1. افتح **Bash console** من لوحة التحكم

2. استنسخ المستودع:
```bash
cd ~
git clone https://github.com/david837838-byte/zozo.git
cd zozo
```

3. إنشاء بيئة افتراضية:
```bash
mkvirtualenv --python=/usr/bin/python3.9 zozo_env
pip install -r requirements.txt
```

4. تكوين التطبيق:

#### الطريقة الثانية: رفع الملفات يدويًا

1. اذهب إلى **Files** في لوحة التحكم
2. اضغط على **Upload a file**
3. اختر جميع الملفات من مشروعك

### 3. تكوين Web App

1. من لوحة التحكم اختر **Web**
2. اضغط **Add a new web app**
3. اختر **Manual configuration** ثم **Python 3.9+**

### 4. تكوين ملف WSGI

1. فتح ملف WSGI عبر **Web > WSGI configuration file**
2. استبدل المحتوى بـ:

```python
import os
import sys

# إضافة مسار المشروع
path = '/home/YOUR_USERNAME/zozo'
if path not in sys.path:
    sys.path.append(path)

# تعيين متغيرات البيئة
os.environ['FLASK_ENV'] = 'production'

from app import create_app
app = create_app()
```

استبدل `YOUR_USERNAME` باسم المستخدم الخاص بك على PythonAnywhere

### 5. تكوين البيئة الافتراضية

1. في **Web > Virtualenv**
2. أدخل المسار: `/home/YOUR_USERNAME/.virtualenvs/zozo_env`

### 6. تكوين الملفات الثابتة (Static Files)

1. في قسم **Static files and directories**
2. أضف:
   - URL: `/static/`
   - Directory: `/home/YOUR_USERNAME/zozo/app/static`

### 7. قاعدة البيانات

- التطبيق سيستخدم SQLite بشكل افتراضي
- سيتم إنشاء `instance/app.db` تلقائيًا عند أول تشغيل

### 8. تفعيل التطبيق

1. اذهب إلى **Web**
2. اضغط الزر الأخضر **Reload**

### 9. اختبار التطبيق

سيكون متاحًا على: `https://YOUR_USERNAME.pythonanywhere.com`

---

## استكشاف الأخطاء

### عرض السجلات (Logs)
```
/var/log/YOUR_USERNAME.pythonanywhere.com.error.log
/var/log/YOUR_USERNAME.pythonanywhere.com.access.log
```

### الاتصال بـ Bash Console للتصحيح
```bash
cd ~/zozo
source ~.virtualenvs/zozo_env/bin/activate
python create_admin.py  # إنشاء حساب admin
```

### إعادة تحميل التطبيق
من لوحة التحكم **Web** اضغط **Reload**

---

## ملاحظات:

1. **الإعدادات**: يمكنك تعديل `config.py` للإعدادات المختلفة
2. **البيانات**: احفظ ملف النسخة الاحتياطية للقاعدة قبل الحذف
3. **الأمان**: غيّر `SECRET_KEY` في config.py قبل الإطلاق
