"""
سكريبت إدارة قاعدة البيانات
Database Management Script
"""

import os
import sys
from datetime import datetime

# إضافة مسار التطبيق
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User

app = create_app()

def init_db():
    """إنشاء وتهيئة قاعدة البيانات"""
    with app.app_context():
        print("جاري إنشاء قاعدة البيانات...")
        db.create_all()
        print("✓ تم إنشاء قاعدة البيانات بنجاح")
        return True

def drop_db():
    """حذف قاعدة البيانات (احذر!)"""
    if input("هل أنت متأكد من حذف كل البيانات؟ (نعم/لا): ").lower() in ['نعم', 'yes']:
        with app.app_context():
            print("جاري حذف قاعدة البيانات...")
            db.drop_all()
            print("✓ تم حذف قاعدة البيانات")
            return True
    print("✗ تم إلغاء الحذف")
    return False

def create_admin():
    """إنشاء حساب مسؤول جديد"""
    with app.app_context():
        username = input('أدخل اسم المستخدم: ').strip()
        
        if User.query.filter_by(username=username).first():
            print('✗ اسم المستخدم موجود بالفعل')
            return False
        
        email = input('أدخل البريد الإلكتروني: ').strip()
        password = input('أدخل كلمة المرور: ').strip()
        full_name = input('أدخل الاسم الكامل: ').strip()
        
        admin = User(
            username=username,
            email=email,
            full_name=full_name,
            is_admin=True,
            is_active=True,
            can_manage_workers=True,
            can_manage_inventory=True,
            can_manage_production=True,
            can_manage_sales=True,
            can_manage_accounting=True,
            can_manage_reports=True,
            can_delete=True,
            can_edit=True
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f'✓ تم إنشاء حساب المسؤول {username} بنجاح')
        return True

def backup_db():
    """عمل نسخة احتياطية من قاعدة البيانات"""
    import shutil
    
    db_file = 'farm_management.db'
    if os.path.exists(db_file):
        backup_file = f'farm_management_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        shutil.copy(db_file, backup_file)
        print(f'✓ تم عمل نسخة احتياطية: {backup_file}')
        return True
    else:
        print('✗ قاعدة البيانات غير موجودة')
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("أداة إدارة قاعدة البيانات")
    print("Database Management Tool")
    print("=" * 60)
    print("\nالخيارات:")
    print("1. إنشاء قاعدة بيانات جديدة")
    print("2. إنشاء حساب مسؤول")
    print("3. حذف قاعدة البيانات")
    print("4. عمل نسخة احتياطية")
    print("0. خروج")
    print("-" * 60)
    
    choice = input('اختر خيار (0-4): ').strip()
    
    if choice == '1':
        init_db()
    elif choice == '2':
        create_admin()
    elif choice == '3':
        drop_db()
    elif choice == '4':
        backup_db()
    elif choice == '0':
        print("وداعاً")
    else:
        print("✗ خيار غير صحيح")
