import getpass
import os

from app import create_app, db
from app.models.account import Account
from app.models.user import User

app = create_app(os.environ.get('FLASK_ENV', 'development'))


def _is_strong_password(password):
    if len(password) < 10:
        return False
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_lower and has_upper and has_digit


def _prompt_password():
    password = getpass.getpass('Enter password: ')
    confirm_password = getpass.getpass('Confirm password: ')
    if password != confirm_password:
        print('Passwords do not match.')
        return None
    if not _is_strong_password(password):
        print(
            'Weak password. Use at least 10 characters with uppercase, '
            'lowercase, and numbers.'
        )
        return None
    return password


def _ensure_default_account():
    account = Account.query.order_by(Account.id.asc()).first()
    if account:
        return account

    account = Account(name='Default Account', is_active=True)
    db.session.add(account)
    db.session.flush()
    return account


@app.shell_context_processor
def make_shell_context():
    """Add models to flask shell context."""
    return {
        'db': db,
        'Account': Account,
        'User': User,
    }


@app.cli.command()
def init_db():
    """Create database tables."""
    db.create_all()
    print('Database tables created.')


@app.cli.command()
def create_admin():
    """
    Create an account admin.
    The first admin in the system becomes Super Admin automatically.
    """
    account_name = input('Account/Company name: ').strip()
    username = input('Username: ').strip()
    email = input('Email: ').strip()
    full_name = input('Full name: ').strip()
    password = _prompt_password()

    if not account_name:
        print('Account name is required.')
        return
    if not username:
        print('Username is required.')
        return
    if not email:
        print('Email is required.')
        return
    if not full_name:
        print('Full name is required.')
        return
    if not password:
        return

    existing_user = (
        User.query.execution_options(tenant_skip=True)
        .filter((User.username == username) | (User.email == email))
        .first()
    )
    if existing_user:
        print('Username or email already exists.')
        return

    account = Account.query.filter_by(name=account_name).first()
    if not account:
        account = Account(name=account_name, is_active=True)
        db.session.add(account)
        db.session.flush()

    has_super_admin = (
        User.query.execution_options(tenant_skip=True)
        .filter_by(is_super_admin=True)
        .count()
        > 0
    )
    is_super_admin = not has_super_admin

    admin = User(
        account_id=account.id,
        username=username,
        email=email,
        full_name=full_name,
        is_admin=True,
        is_super_admin=is_super_admin,
        is_active=True,
        can_manage_workers=True,
        can_manage_inventory=True,
        can_manage_production=True,
        can_manage_sales=True,
        can_manage_accounting=True,
        can_manage_reports=True,
        can_delete=True,
        can_edit=True,
    )
    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    if is_super_admin:
        print(f'Created first Super Admin: {username}')
    else:
        print(f'Created account admin: {username} (Super Admin unchanged)')


@app.cli.command()
def reset_super_admin():
    """
    Create or reset a Super Admin account credentials.
    """
    username = input('Super Admin username [superadmin]: ').strip() or 'superadmin'
    email = input('Email [superadmin@farm.local]: ').strip() or 'superadmin@farm.local'
    full_name = input('Full name [Super Admin]: ').strip() or 'Super Admin'
    password = _prompt_password()

    if not password:
        return

    account = _ensure_default_account()

    user = (
        User.query.execution_options(tenant_skip=True)
        .filter_by(username=username)
        .first()
    )
    if not user:
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            account_id=account.id,
            is_active=True,
            is_admin=True,
            is_super_admin=True,
            can_manage_workers=True,
            can_manage_inventory=True,
            can_manage_production=True,
            can_manage_sales=True,
            can_manage_accounting=True,
            can_manage_reports=True,
            can_delete=True,
            can_edit=True,
            can_manage_crop_health=True,
            can_manage_production_batches=True,
            can_manage_production_costs=True,
            can_manage_production_stages=True,
            can_view_analytics=True,
        )
        db.session.add(user)

    user.email = email
    user.full_name = full_name
    user.account_id = account.id
    user.is_active = True
    user.is_admin = True
    user.is_super_admin = True
    user.can_manage_workers = True
    user.can_manage_inventory = True
    user.can_manage_production = True
    user.can_manage_sales = True
    user.can_manage_accounting = True
    user.can_manage_reports = True
    user.can_delete = True
    user.can_edit = True
    user.can_manage_crop_health = True
    user.can_manage_production_batches = True
    user.can_manage_production_costs = True
    user.can_manage_production_stages = True
    user.can_view_analytics = True
    user.set_password(password)

    db.session.commit()
    print(f'Reset Super Admin successfully: {username}')


if __name__ == '__main__':
    app.run(debug=True)
