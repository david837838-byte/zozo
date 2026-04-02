#!/bin/bash

# Farm Management System - Quick Start Script

echo "نظام إدارة المزرعة - سكريبت البدء السريع"
echo "======================================"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "خطأ: Python 3 غير مثبت. يرجى تثبيت Python 3 أولاً."
    exit 1
fi

echo "✓ تم العثور على Python 3"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "إنشاء بيئة افتراضية..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "تفعيل البيئة الافتراضية..."
source venv/bin/activate

# Install dependencies
echo "تثبيت المكتبات المطلوبة..."
pip install -r requirements.txt

# Initialize database
echo "إنشاء قاعدة البيانات..."
python run.py shell << EOF
from app import db
db.create_all()
print('تم إنشاء قاعدة البيانات بنجاح')
exit()
EOF

# Create admin user
echo ""
echo "إنشاء حساب مسؤول جديد"
echo "--------------------"
python run.py create-admin

echo ""
echo "✓ انتهى الإعداد بنجاح!"
echo ""
echo "لتشغيل التطبيق، استخدم:"
echo "    python run.py"
echo ""
echo "ثم زر: http://localhost:5000"
