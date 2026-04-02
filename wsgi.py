"""
نقطة دخول تطبيق Flask
Flask Application Entry Point
"""

import os
import sys

# إضافة مسار التطبيق إلى Python path
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# تعيين متغيرات البيئة للإنتاج
os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app, db

# إنشاء التطبيق
app = create_app(os.environ.get('FLASK_ENV', 'production'))

# إنشاء جداول قاعدة البيانات إن لم تكن موجودة
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        app.logger.error(f"Error creating database tables: {e}")

if __name__ == '__main__':
    app.run(debug=False)
