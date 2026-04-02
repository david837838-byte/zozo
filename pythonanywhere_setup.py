#!/usr/bin/env python
"""
سكريبت مساعد لإعداد التطبيق على PythonAnywhere
Helper script for setting up the application on PythonAnywhere
"""

import os
import sys
import subprocess
from pathlib import Path

# إضافة مسار المشروع
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def run_command(cmd, description=""):
    """تشغيل أمر من سطر الأوامر"""
    if description:
        print(f"\n📝 {description}")
    print(f"  Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.returncode != 0 and result.stderr:
            print(f"⚠️  Warning: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def setup_database():
    """إعداد قاعدة البيانات"""
    print("\n🗄️  Setting up database...")
    
    os.chdir(project_root)
    
    # تشغيل سكريبت إنشاء قاعدة البيانات
    if Path('init_db.py').exists():
        result = run_command(f"{sys.executable} init_db.py", 
                            "Initializing database...")
        return result
    
    # أو إنشاء الجداول من التطبيق
    try:
        from app import create_app, db
        app = create_app('production')
        with app.app_context():
            db.create_all()
            print("✅ Database tables created successfully!")
            return True
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False

def install_requirements():
    """تثبيت المكتبات المطلوبة"""
    print("\n📦 Installing requirements...")
    
    if Path('requirements.txt').exists():
        return run_command(f"{sys.executable} -m pip install -r requirements.txt",
                          "Installing Python packages...")
    else:
        print("❌ requirements.txt not found!")
        return False

def create_admin_user():
    """إنشاء حساب admin"""
    print("\n👤 Creating admin user...")
    
    if Path('create_admin.py').exists():
        return run_command(f"{sys.executable} create_admin.py",
                          "Running admin creation script...")
    else:
        print("⚠️  create_admin.py not found. You'll need to create admin manually.")
        return False

def check_directories():
    """التحقق من وجود المجلدات الضرورية"""
    print("\n📂 Checking directories...")
    
    required_dirs = [
        'app/static',
        'app/templates',
        'instance',
        'instance/backups'
    ]
    
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {dir_path} exists")
    
    return True

def verify_wsgi():
    """التحقق من ملف WSGI"""
    print("\n⚙️  Verifying WSGI configuration...")
    
    if Path('wsgi.py').exists():
        try:
            from wsgi import app
            print("✅ WSGI file loads correctly!")
            return True
        except Exception as e:
            print(f"❌ Error loading WSGI: {e}")
            return False
    else:
        print("❌ wsgi.py not found!")
        return False

def main():
    """الدالة الرئيسية"""
    print("""
    ╔════════════════════════════════════════╗
    ║   Farm Management System Setup         ║
    ║   نظام إدارة المزرعة - الإعداد        ║
    ╚════════════════════════════════════════╝
    """)
    
    print(f"📍 Project root: {project_root}")
    print(f"🐍 Python version: {sys.version}")
    
    # تشغيل خطوات الإعداد
    steps = [
        ("Checking directories", check_directories),
        ("Verifying WSGI", verify_wsgi),
        ("Installing requirements", install_requirements),
        ("Setting up database", setup_database),
    ]
    
    results = {}
    for step_name, step_func in steps:
        try:
            results[step_name] = step_func()
        except Exception as e:
            print(f"❌ Error in {step_name}: {e}")
            results[step_name] = False
    
    # الملخص النهائي
    print("\n" + "="*50)
    print("📊 Setup Summary:")
    print("="*50)
    
    for step, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {step}")
    
    all_success = all(results.values())
    
    if all_success:
        print("\n✨ Setup completed successfully!")
        print("\n📌 Next steps:")
        print("1. Configure WSGI on PythonAnywhere:")
        print("   /home/YOUR_USERNAME/.virtualenvs/YOUR_ENV/lib/pythonX.X/site-packages/")
        print("2. Set up virtual environment")
        print("3. Configure static files")
        print("4. Reload the web app")
        print("\n🌐 Your app will be available at:")
        print("   https://YOUR_USERNAME.pythonanywhere.com")
    else:
        print("\n⚠️  Setup completed with errors. Please check the logs above.")
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⛔ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
