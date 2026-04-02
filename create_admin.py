#!/usr/bin/env python
"""
سكريبت لإنشاء حساب مسؤول بسرعة
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # بيانات الـ Admin
    username = "admin"
    email = "admin@farm.local"
    password = "admin123"  # كلمة مرور افتراضية
    full_name = "مسؤول النظام"
    
    # التحقق من وجود المستخدم
    if User.query.filter_by(username=username).first():
        print(f'✗ حساب {username} موجود بالفعل')
        sys.exit(1)
    
    # إنشاء حساب الـ Admin
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
        can_edit=True,
        # الصلاحيات المتقدمة للإنتاج
        can_manage_crop_health=True,
        can_manage_production_batches=True,
        can_manage_production_costs=True,
        can_manage_production_stages=True,
        can_view_analytics=True
    )
    admin.set_password(password)
    
    db.session.add(admin)
    db.session.commit()
    
    print("=" * 60)
    print("✓ تم إنشاء حساب مسؤول جديد")
    print("=" * 60)
    print(f"اسم المستخدم: {username}")
    print(f"كلمة المرور: {password}")
    print(f"البريد الإلكتروني: {email}")
    print("=" * 60)
