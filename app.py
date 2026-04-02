"""
نظام إدارة المزرعة المتكامل
Farm Management System - Entry Point

هذا الملف يقوم بتشغيل التطبيق
"""

import os
import sys
from flask import render_template

# إضافة مسار التطبيق إلى Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

# إنشاء التطبيق
app = create_app(os.environ.get('FLASK_ENV', 'development'))

# معالجات الأخطاء
@app.errorhandler(404)
def not_found(error):
    """صفحة 404"""
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(error):
    """صفحة 403"""
    return render_template('403.html'), 403

@app.errorhandler(500)
def server_error(error):
    """صفحة 500"""
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    print("=" * 60)
    print("نظام إدارة المزرعة المتكامل")
    print("Farm Management System")
    print("=" * 60)
    print(f"البيئة: {os.environ.get('FLASK_ENV', 'development')}")
    print(f"المنفذ: 5000")
    print(f"الرابط: http://localhost:5000")
    print("=" * 60)
    print("اضغط Ctrl+C للإيقاف\n")
    
    # تشغيل التطبيق
    app.run(debug=True, host='0.0.0.0', port=5000)
