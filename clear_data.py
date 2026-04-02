#!/usr/bin/env python
"""
سكريبت لحذف جميع البيانات من قاعدة البيانات
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

app = create_app()

with app.app_context():
    print("جاري حذف جميع البيانات...")
    try:
        db.drop_all()
        print("✓ تم حذف جميع الجداول")
        
        print("\nجاري إنشاء قاعدة البيانات من جديد...")
        db.create_all()
        print("✓ تم إنشاء قاعدة البيانات")
        
        print("\n✓ تم مسح جميع البيانات بنجاح!")
        
    except Exception as e:
        print(f"✗ حدث خطأ: {str(e)}")
        sys.exit(1)
