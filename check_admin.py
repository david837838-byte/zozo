from app import create_app

app = create_app()
with app.app_context():
    from app.models.user import User
    admin = User.query.filter_by(username='admin').first()
    if admin:
        print('=' * 60)
        print('✓ بيانات حساب admin:')
        print('=' * 60)
        print(f'اسم المستخدم: {admin.username}')
        print(f'is_admin: {admin.is_admin}')
        print(f'is_super_admin: {admin.is_super_admin}')
        print(f'account_id: {admin.account_id}')
        print(f'is_active: {admin.is_active}')
        print('=' * 60)
        if admin.is_super_admin:
            print('✅ الحساب صحيح - يمكن إدارة المستخدمين')
        else:
            print('❌ الحساب ليس super_admin')
    else:
        print('❌ لم يتم العثور على admin')
