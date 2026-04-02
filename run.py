import os
from app import create_app, db
from app.models.user import User

app = create_app(os.environ.get('FLASK_ENV', 'development'))

@app.shell_context_processor
def make_shell_context():
    """إضافة نماذج إلى سياق الـ shell"""
    return {
        'db': db,
        'User': User
    }

@app.cli.command()
def init_db():
    """إنشاء قاعدة البيانات"""
    db.create_all()
    print('تم إنشاء قاعدة البيانات')

@app.cli.command()
def create_admin():
    """إنشاء حساب مسؤول"""
    username = input('أدخل اسم المستخدم: ')
    email = input('أدخل البريد الإلكتروني: ')
    password = input('أدخل كلمة المرور: ')
    full_name = input('أدخل الاسم الكامل: ')
    
    if User.query.filter_by(username=username).first():
        print('اسم المستخدم موجود بالفعل')
        return
    
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
    
    print(f'تم إنشاء حساب المسؤول {username} بنجاح')

if __name__ == '__main__':
    app.run(debug=True)
