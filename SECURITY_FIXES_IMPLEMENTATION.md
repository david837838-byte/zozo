# الحلول الأمنية الفورية
## تحسينات أمان سريعة وفعالة

---

## 1️⃣ تحسين قوة كلمات المرور

### ملف جديد: `app/password_validator.py`
```python
import re
from zxcvbn import zxcvbn

def validate_password_strength(password):
    """
    تحقق من قوة كلمة المرور
    العودة: (valid, message)
    """
    
    # الحد الأدنى للطول
    if len(password) < 12:
        return False, "يجب أن تكون كلمة المرور على الأقل 12 حرف"
    
    # التحقق من تنوع الأحرف
    if not re.search(r'[a-z]', password):
        return False, "يجب أن تحتوي على أحرف إنجليزية صغيرة (a-z)"
    
    if not re.search(r'[A-Z]', password):
        return False, "يجب أن تحتوي على أحرف إنجليزية كبيرة (A-Z)"
    
    if not re.search(r'[0-9]', password):
        return False, "يجب أن تحتوي على أرقام (0-9)"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>[\]\\]', password):
        return False, "يجب أن تحتوي على رموز خاصة (!@#$%^&* إلخ)"
    
    # فحص الكلمات الشهيرة باستخدام zxcvbn
    try:
        result = zxcvbn(password)
        if result['score'] < 2:  # يحتاج على الأقل درجة 2
            return False, "كلمة المرور ضعيفة جداً - تجنب الأنماط والكلمات الشهيرة"
    except Exception:
        pass
    
    return True, "كلمة المرور قوية وآمنة"
```

### تحديث `app/routes/auth.py`
```python
# أضف في الأعلى
from app.password_validator import validate_password_strength

# في دالة change_password
if request.method == 'POST':
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_user.check_password(current_password):
        flash('كلمة المرور الحالية غير صحيحة', 'danger')
        return redirect(url_for('auth.change_password'))

    if new_password != confirm_password:
        flash('كلمات المرور الجديدة غير متطابقة', 'danger')
        return redirect(url_for('auth.change_password'))

    # ✅ استخدم مدقق القوة الجديد
    is_valid, message = validate_password_strength(new_password)
    if not is_valid:
        flash(f'كلمة المرور ضعيفة: {message}', 'danger')
        return redirect(url_for('auth.change_password'))

    current_user.set_password(new_password)
    db.session.commit()
    flash('تم تغيير كلمة المرور بنجاح', 'success')
    return redirect(url_for('home.index'))
```

---

## 2️⃣ إضافة رؤوس الأمان

### ملف جديد: `app/security_headers.py`
```python
from flask import Blueprint

def setup_security_headers(app):
    """تطبيق رؤوس الأمان على جميع الاستجابات"""
    
    @app.after_request
    def set_security_headers(response):
        # منع MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # منع Clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # سياسة أمان المحتوى (Content Security Policy)
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com cdnjs.cloudflare.com; "
            "font-src 'self' fonts.gstatic.com cdnjs.cloudflare.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        )
        
        # HTTPS فقط (في الإنتاج)
        if app.config.get('ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # منع CORS
        response.headers['Access-Control-Allow-Origin'] = 'self'
        
        # معلومات الخادم
        response.headers['Server'] = 'Protected'
        
        return response
```

### تحديث `app/__init__.py`
```python
from app.security_headers import setup_security_headers

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # ... كود آخر ...
    
    # تطبيق رؤوس الأمان
    setup_security_headers(app)
    
    return app
```

---

## 3️⃣ حماية جميع عمليات POST من CSRF

### تحديث `app/__init__.py`
```python
@app.before_request
def enforce_csrf_on_all_post():
    """تطبيق CSRF على جميع طلبات POST"""
    if request.method == "POST":
        # استبعد بعض الطلبات الآمنة إن لزم
        skip_csrf_paths = []
        
        if request.path in skip_csrf_paths:
            return None
        
        submitted_token = get_submitted_csrf_token()
        if not validate_csrf_token(submitted_token):
            db.session.rollback()
            flash("رمز الأمان غير صالح. يرجى إعادة المحاولة", "danger")
            return redirect(request.referrer or url_for("home.index")), 403
```

---

## 4️⃣ تطبيق Rate Limiting

### تثبيت المكتبة
```bash
pip install Flask-Limiter
```

### ملف جديد: `app/rate_limiter.py`
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

def init_rate_limiter(app):
    limiter.init_app(app)
    return limiter
```

### تحديث `app/__init__.py`
```python
from app.rate_limiter import init_rate_limiter

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # ... كود آخر ...
    
    # تطبيق Rate Limiting
    limiter = init_rate_limiter(app)
    
    return app
```

### تحديث `app/routes/auth.py`
```python
from app import limiter

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # 5 محاولات فقط
def login():
    # ... كود المصادقة ...
```

---

## 5️⃣ تحسين متغيرات البيئة

### ملف جديد: `.env.example`
```
# Flask Config
FLASK_ENV=production
FLASK_DEBUG=False

# Security
SECRET_KEY=your-very-long-random-secret-key-here-change-this
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True

# Database
DATABASE_URL=postgresql://user:password@localhost/farm_db

# AI APIs (اختياري)
GEMINI_API_KEY=your-gemini-key
GOOGLE_API_KEY=your-google-key
OPENAI_API_KEY=your-openai-key

# Email (للتنبيهات الأمنية)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### تحديث `config.py`
```python
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    
    # SECRET_KEY يجب أن يكون موجود في البيئة
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "ERROR: SECRET_KEY must be set in environment variables. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///farm_management.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # AI APIs
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash').strip()

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # يجب أن يكون True في الإنتاج
```

---

## 6️⃣ إضافة Timeout للجلسات

### تحديث `config.py`
```python
from datetime import timedelta

class Config:
    # Timeout الجلسة
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  # 30 دقيقة
    
    # إعدادات الـ Cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    SESSION_REFRESH_EACH_REQUEST = True  # تجديد الجلسة مع كل طلب
```

### تحديث `app/__init__.py`
```python
@app.before_request
def refresh_session_timeout():
    """تجديد مدة انتهاء الجلسة مع كل طلب"""
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=30)
```

---

## 7️⃣ تسجيل محاولات الدخول الفاشلة

### تحديث `app/routes/auth.py`
```python
from app.models.audit_log import AuditLog

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # ... كود تسجيل الدخول الناجح ...
            AuditLog.log_security_event(
                event_type='successful_login',
                user_id=user.id,
                ip_address=request.remote_addr,
                details=f"تسجيل دخول ناجح من {request.remote_addr}"
            )
        else:
            # ❌ تسجيل محاولة فاشلة
            AuditLog.log_security_event(
                event_type='failed_login_attempt',
                user_identifier=username,
                ip_address=request.remote_addr,
                details=f"محاولة دخول فاشلة - المستخدم: {username}"
            )
            
            # اقفل الحساب بعد محاولات متعددة
            failed_attempts = AuditLog.query.filter(
                AuditLog.event_type == 'failed_login_attempt',
                AuditLog.user_identifier == username,
                AuditLog.created_at > datetime.utcnow() - timedelta(minutes=15)
            ).count()
            
            if failed_attempts >= 5:
                flash(
                    'تم إيقاف حسابك مؤقتاً بعد محاولات دخول متعددة. تواصل مع الإدارة.',
                    'danger'
                )
                return redirect(url_for('auth.login'))
            
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('auth/login.html')
```

---

## 8️⃣ إضافة Logging الأمني

### ملف جديد: `app/security_logger.py`
```python
import logging
from logging.handlers import RotatingFileHandler
import os

def setup_security_logger(app):
    """إعداد logger للأحداث الأمنية"""
    
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Security logger
    security_handler = RotatingFileHandler(
        'logs/security.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    
    security_logger = logging.getLogger('security')
    security_logger.setLevel(logging.WARNING)
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s [in %(filename)s:%(lineno)d]'
    )
    security_handler.setFormatter(formatter)
    security_logger.addHandler(security_handler)
    
    return security_logger

# الاستخدام
security_logger = setup_security_logger(None)

def log_security_event(event_type, details, severity='warning'):
    """تسجيل حدث أمني"""
    security_logger.log(
        logging.WARNING if severity == 'warning' else logging.ERROR,
        f"[{event_type}] {details}"
    )
```

---

## 9️⃣ حماية من Upload الملفات الخطرة

### تحديث `app/routes/ai_assistant.py`
```python
import magic
import os
import secrets

def validate_uploaded_file(file_data, filename):
    """التحقق من صحة الملف المُحمّل"""
    
    # 1. تحقق من الحجم
    if len(file_data) > _MAX_UPLOAD_IMAGE_BYTES:
        raise ValueError(f"الملف كبير جداً (الحد الأقصى: {_MAX_UPLOAD_IMAGE_BYTES} بايت)")
    
    # 2. تحقق من نوع MIME
    try:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(file_data)
        
        if not mime_type.startswith(_ALLOWED_UPLOAD_MIME_PREFIX):
            raise ValueError(f"نوع ملف غير مسموح: {mime_type}")
    except Exception as e:
        raise ValueError(f"فشل التحقق من نوع الملف: {str(e)}")
    
    # 3. تحقق من امتداد الملف
    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext not in allowed_extensions:
        raise ValueError(f"امتداد ملف غير مسموح: {file_ext}")
    
    return True

def save_uploaded_file_safely(file):
    """حفظ الملف بشكل آمن"""
    
    file_data = file.read()
    original_filename = file.filename
    
    # تحقق من الملف
    validate_uploaded_file(file_data, original_filename)
    
    # أنشئ اسماً عشوائياً
    file_ext = original_filename.rsplit('.', 1)[1].lower()
    random_filename = f"{secrets.token_hex(16)}.{file_ext}"
    
    # أنشئ مسار آمن
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, random_filename)
    
    # تحقق من أن المسار آمن (لا directory traversal)
    if not os.path.abspath(file_path).startswith(os.path.abspath(upload_dir)):
        raise ValueError("مسار الملف غير آمن")
    
    # احفظ الملف
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return random_filename
```

---

## 🔟 تحديث متطلبات المشروع

### تحديث `requirements.txt`
```
blinker==1.9.0
click==8.3.1
colorama==0.4.6
arabic-reshaper==3.0.0
Flask==2.3.3
Flask-Login==0.6.2
Flask-SQLAlchemy==3.0.3
Flask-WTF==1.1.1
greenlet==3.3.1
itsdangerous==2.2.0
Jinja2==3.1.2
MarkupSafe==2.1.1
openpyxl==3.1.5
python-bidi==0.4.2
python-dateutil==2.8.2
reportlab==4.4.10
six==1.17.0
SQLAlchemy==2.0.46
typing_extensions==4.15.0
Werkzeug==2.3.8
WTForms==3.0.1

# أمان
Flask-Limiter==3.5.0
python-zxcvbn==4.4.28
python-magic==0.4.27
cryptography==41.0.0

# تسجيل وتحليل
python-dotenv==1.0.0
```

---

## تعليمات التطبيق الفوري

### 1. تثبيت المكتبات الجديدة
```bash
pip install -r requirements.txt
```

### 2. إعداد المتغيرات البيئية
```bash
# انسخ الملف
cp .env.example .env

# حدد القيم الخاصة بك
# أهمها: SECRET_KEY
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
```

### 3. التحقق من الأمان
```bash
# اختبر XSS
# اختبر SQL Injection
# اختبر CSRF
# اختبر Rate Limiting
```

### 4. النشر
```bash
# تأكد من HTTPS
# تأكد من البيانات الحساسة في .env
# تفعيل HTTPS فقط
# تفعيل رؤوس الأمان
```

---

**ملاحظة مهمة:** هذه الحلول تحتاج إلى اختبار شامل قبل الاستخدام في الإنتاج.
