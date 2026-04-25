"""
نقطة دخول تطبيق Flask للإنتاج
Flask Production Entry Point for PythonAnywhere
"""

import os
import sys
from pathlib import Path

# الحصول على مسار المشروع الحالي
project_root = str(Path(__file__).parent.absolute())

# إضافة المشروع إلى Python path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# تعيين البيئة للإنتاج
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('FLASK_DEBUG', 'False')

# تحميل متغيرات البيئة من .env (إن وجدت)
try:
    from dotenv import load_dotenv
    env_file = Path(project_root) / '.env'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

# استيراد التطبيق
try:
    from app import create_app, db
    
    # إنشاء تطبيق الإنتاج
    application = create_app('production')
    
    # إنشاء جداول قاعدة البيانات إذا لم تكن موجودة
    with application.app_context():
        try:
            db.create_all()
            application.logger.info("Database tables checked/created successfully")
        except Exception as db_error:
            application.logger.error(f"Database initialization error: {db_error}")
    
    application.logger.info("Application started successfully in production mode")
    
except Exception as e:
    import traceback
    error_msg = f"Failed to load application: {str(e)}\n{traceback.format_exc()}"
    print(error_msg, file=sys.stderr)
    
    # تطبيق بديل في حالة الفشل
    from flask import Flask
    application = Flask(__name__)
    
    @application.route('/')
    def error():
        return f"<h1>Application Error</h1><pre>{error_msg}</pre>", 500

# للتطوير المحلي فقط
if __name__ == '__main__':
    application.run(debug=False, host='127.0.0.1', port=5000)
