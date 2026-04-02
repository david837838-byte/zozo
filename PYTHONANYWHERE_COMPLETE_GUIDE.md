# شرح شامل: نشر تطبيق إدارة المزرعة على PythonAnywhere
# Complete Guide: Deploying Farm Management System to PythonAnywhere

## 📌 ملخص سريع (Quick Summary)

يحتوي هذا المجلد على كل ما تحتاجه لنشر التطبيق. خطوات النشر موضحة أدناه.

---

## 🚀 الطريقة السريعة (Quick Method)

### إذا كنت تستخدم Bash (Linux/Mac/WSL):

```bash
# 1. ادخل إلى PythonAnywhere Bash console
bash deploy.sh your_username zozo_env

# 2. انتظر اكتمال البرنامج
# 3. اتبع التعليمات النهائية في لوحة التحكم
```

### إذا كنت تستخدم Windows PowerShell:

استخدم الخطوات اليدوية أدناه ✓

---

## 📋 الخطوات اليدوية (Manual Steps)

### المرحلة 1: الإعداد الأولي

#### 1.1 إنشاء حساب على PythonAnywhere
- زيارة: https://www.pythonanywhere.com
- اضغط "Sign up" واختر الخطة المجانية
- أكمل التسجيل

#### 1.2 فتح Bash Console
- في لوحة التحكم اختر **Consoles**
- انقر على **Bash Console** لفتح terminal

---

### المرحلة 2: هبوط التطبيق

#### 2.1 استنسخ المستودع
```bash
cd ~
git clone https://github.com/david837838-byte/zozo.git
cd zozo
```

#### 2.2 التحقق من البنية
```bash
ls -la
pwd  # يجب أن يعرض: /home/YOUR_USERNAME/zozo
```

---

### المرحلة 3: إعداد البيئة الافتراضية

#### 3.1 إنشاء البيئة الافتراضية
```bash
mkvirtualenv --python=/usr/bin/python3.9 zozo_env
```

**ملاحظة:** اسم البيئة يمكن أن يكون أي شيء (مثل: `my_farm_env`)

#### 3.2 البيئة الافتراضية تكون مفعلة افتراضيًا
```bash
# يجب أن ترى (zozo_env) أمام سطر الأوامر
# مثل: (zozo_env) 17:45 ~ $
```

#### 3.3 تثبيت المكتبات
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**الوقت المتوقع:** 5-10 دقائق

#### 3.4 التحقق من التثبيت
```bash
python -c "import flask; print(flask.__version__)"
# يجب أن يطبع: 2.3.3
```

---

### المرحلة 4: إعداد قاعدة البيانات

#### 4.1 إنشاء قاعدة البيانات
```bash
python init_db.py
```

أو إذا لم يعمل:
```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

#### 4.2 التحقق من قاعدة البيانات
```bash
ls -la instance/
# يجب أن ترى ملف: farm_management.db
```

---

### المرحلة 5: إعداد حساب Admin (اختياري)

#### 5.1 إنشاء مستخدم Admin
```bash
python create_admin.py
```

#### 5.2 اتبع التعليمات
```
Username: admin
Email: admin@farm.local
Password: (اختر كلمة سر قوية)
```

---

### المرحلة 6: تكوين التطبيق على Dashboard

#### 6.1 الذهاب إلى Web Tab
1. في لوحة التحكم اختر **Web**
2. انقر **Add a new web app**

#### 6.2 اختيار Framework
- اختر **Manual configuration**
- اختر **Python 3.9**

#### 6.3 تحرير WSGI Configuration File

في قسم **Code** للـ Web app:
- اضغط على ملف WSGI (الرابط الأزرق)
- احذف كل المحتوى
- الصق هذا الكود:

```python
import os
import sys

# إضافة مسار المشروع
path = '/home/YOUR_USERNAME/zozo'
if path not in sys.path:
    sys.path.append(path)

# تفعيل وضع الإنتاج
os.environ['FLASK_ENV'] = 'production'

# تحميل التطبيق
from wsgi import app

# إنشاء جداول البيانات إذا لم تكن موجودة
with app.app_context():
    try:
        from app import db
        db.create_all()
    except:
        pass
```

**⚠️ تهم جدًا:** استبدل `YOUR_USERNAME` باسم المستخدم الفعلي على PythonAnywhere

#### 6.4 تعيين البيئة الافتراضية

في **Virtualenv**:
- أدخل هذا المسار:
```
/home/YOUR_USERNAME/.virtualenvs/zozo_env
```

#### 6.5 تكوين الملفات الثابتة (Static Files)

في **Static files and directories**:
- اضغط **Add a new static files mapping**
- **URL:** `/static/`
- **Directory:** `/home/YOUR_USERNAME/zozo/app/static`

**ملاحظة:** قد لا تحتاج هذا إذا كان التطبيق يستخدم CDN

---

### المرحلة 7: التفعيل

#### 7.1 إعادة تحميل التطبيق
1. اذهب إلى **Web** tab
2. اضغط الزر **Reload** (الأخضر الكبير)
3. انتظر ثانية أو اثنتين

#### 7.2 اختبار التطبيق
قم بزيارة: `https://YOUR_USERNAME.pythonanywhere.com`

---

## ✅ اختبار التطبيق

### علامات النجاح:
- ✓ تحميل الصفحة الرئيسية
- ✓ إمكانية تسجيل الدخول
- ✓ لا توجد أخطاء 500

### الصفحات الأساسية:
- `https://YOUR_USERNAME.pythonanywhere.com/` - الرئيسية
- `https://YOUR_USERNAME.pythonanywhere.com/login` - تسجيل الدخول
- `https://YOUR_USERNAME.pythonanywhere.com/dashboard` - لوحة التحكم

---

## 🔧 استكشاف الأخطاء

### عرض السجلات (Logs)

في **Web** tab scrolldown للأسفل لرؤية:
- **Error log:** `/var/log/YOUR_USERNAME.pythonanywhere.com.error.log`
- **Access log:** `/var/log/YOUR_USERNAME.pythonanywhere.com.access.log`

### الخطأ الشائع: 500 Internal Server Error

**الحل:**
1. تحقق من ملف WSGI (هل تم تعديل `YOUR_USERNAME`؟)
2. تحقق من البيئة الافتراضية (هل المسار صحيح؟)
3. اضغط **Reload** مرة أخرى

### عدم تحميل الملفات الثابتة (CSS/JS)

**الحل:**
1. تأكد من تكوين static files
2. استخدم أمر reload
3. امسح ذاكرة تخزين المتصفح (Ctrl+Shift+Delete)

---

## 🔐 تأمين التطبيق للإنتاج

### ⚠️ قبل الإطلاق العلني:

#### 1. تغيير SECRET_KEY
```bash
cd ~/zozo
python -c "import secrets; print(secrets.token_hex(32))"
```

انسخ الناتج ثم اذهب إلى:
- **Web > WSGI configuration file**
- أضف في البداية:
```python
os.environ['SECRET_KEY'] = 'PASTE_THE_KEY_HERE'
```

#### 2. تعطيل وضع DEBUG
```python
app = create_app('production')  # بدلاً من 'development'
```

#### 3. تحديث متغيرات البيانات الحساسة
في `config.py` أو عبر متغيرات البيئة.

---

## 📱 نصائح إضافية

### للعمل على سطح مكتبك (يمكنك فعل التغييرات هنا):
```bash
# 1. اعمل على التطبيق محليًا
# 2. اختبر التغييرات
# 3. ارفعها إلى GitHub:

git add .
git commit -m "Description of changes"
git push origin main
```

### ثم على PythonAnywhere:
```bash
cd ~/zozo
git pull origin main
# أعد تحميل التطبيق من Dashboard
```

---

## 📞 الدعم والمساعدة

### المراجع الرسمية:
- [PythonAnywhere Help](https://help.pythonanywhere.com/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)

### الأسئلة الشائعة:
- **س: كيف أشغل الأوامر بعد الإغلاق؟**
  ج: افتح Bash console جديد و activate البيئة مجددًا

- **س: كيف أنسخ البيانات الاحتياطية؟**
  ج: ادخل إلى Files > instance > download farm_management.db

- **س: هل يمكن استخدام قاعدة بيانات أخرى؟**
  ج: نعم، عدّل SQLALCHEMY_DATABASE_URI في config.py

---

## 🎉 تهانينا!
تطبيقك الآن يعمل على الإنترنت!

اذهب إلى: `https://YOUR_USERNAME.pythonanywhere.com` وابدأ الاستخدام 🚀
