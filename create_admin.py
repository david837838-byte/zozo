#!/usr/bin/env python
"""
Create a Super Admin account securely (no hardcoded credentials).
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.account import Account
from app.models.user import User


def _prompt_value(prompt_text, default=None):
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt_text}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("This field is required.")


def _is_strong_password(password):
    if len(password) < 10:
        return False
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_lower and has_upper and has_digit


def _prompt_password():
    while True:
        password = getpass.getpass("Super Admin password: ")
        confirm = getpass.getpass("Confirm password: ")

        if password != confirm:
            print("Passwords do not match. Try again.")
            continue

        if not _is_strong_password(password):
            print(
                "Weak password. Use at least 10 characters with uppercase, "
                "lowercase, and numbers."
            )
            continue

        return password


def _get_value(env_key, prompt_text, default=None):
    env_value = os.environ.get(env_key, "").strip()
    if env_value:
        return env_value
    return _prompt_value(prompt_text, default=default)


def main():
    app = create_app()

    with app.app_context():
        account_name = _get_value(
            "SUPER_ADMIN_ACCOUNT_NAME",
            "Account name for Super Admin",
            default="النظام الافتراضي",
        )
        username = _get_value(
            "SUPER_ADMIN_USERNAME",
            "Super Admin username",
        )
        email = _get_value("SUPER_ADMIN_EMAIL", "Super Admin email")
        full_name = _get_value(
            "SUPER_ADMIN_FULL_NAME",
            "Super Admin full name",
            default="Super Administrator",
        )
        password = os.environ.get("SUPER_ADMIN_PASSWORD", "").strip()
        if not password:
            password = _prompt_password()
        elif not _is_strong_password(password):
            print(
                "ERROR: SUPER_ADMIN_PASSWORD is weak. "
                "Use at least 10 chars with uppercase, lowercase, and numbers."
            )
            sys.exit(1)

        existing_user = (
            User.query.execution_options(tenant_skip=True)
            .filter(
                (User.username == username) | (User.email == email)
            )
            .first()
        )
        if existing_user:
            print("ERROR: username or email already exists.")
            sys.exit(1)

        account = Account.query.filter_by(name=account_name).first()
        if not account:
            account = Account(name=account_name, is_active=True)
            db.session.add(account)
            db.session.flush()

        admin = User(
            account_id=account.id,
            username=username,
            email=email,
            full_name=full_name,
            is_admin=True,
            is_super_admin=True,
            is_active=True,
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
        admin.set_password(password)

        try:
            db.session.add(admin)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR: failed to create Super Admin: {exc}")
            sys.exit(1)

        print("=" * 70)
        print("Super Admin created successfully")
        print("=" * 70)
        print(f"Account : {account.name}")
        print(f"Username: {username}")
        print(f"Email   : {email}")
        print(f"Name    : {full_name}")
        print("Password: [hidden]")
        print("=" * 70)


if __name__ == "__main__":
    main()
