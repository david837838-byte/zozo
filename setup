@echo off
REM Farm Management System - Quick Start Script for Windows

echo نظام إدارة المزرعة - سكريبت البدء السريع
echo ======================================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo خطأ: Python غير مثبت. يرجى تثبيت Python أولاً.
    pause
    exit /b 1
)

echo. تم العثور على Python

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo إنشاء بيئة افتراضية...
    python -m venv venv
)

REM Activate virtual environment
echo تفعيل البيئة الافتراضية...
call venv\Scripts\activate.bat

REM Install dependencies
echo تثبيت المكتبات المطلوبة...
pip install -r requirements.txt

REM Initialize database
echo إنشاء قاعدة البيانات...
python run.py shell
(
    echo from app import db
    echo db.create_all^(^)
    echo print^('تم إنشاء قاعدة البيانات بنجاح'^)
    echo exit^(^)
) | python -i run.py

REM Create admin user
echo.
echo إنشاء حساب مسؤول جديد
echo --------------------
python run.py create-admin

echo.
echo انتهى الإعداد بنجاح!
echo.
echo لتشغيل التطبيق، استخدم:
echo     python run.py
echo.
echo ثم زر: http://localhost:5000
pause
