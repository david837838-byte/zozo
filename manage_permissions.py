#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""إدارة صلاحيات المستخدمين"""

from app import create_app, db
from app.models.user import User

app = create_app()

def show_users():
    """عرض قائمة المستخدمين"""
    print("\n" + "="*80)
    print("📋 قائمة المستخدمين")
    print("="*80)
    users = User.query.all()
    for user in users:
        admin_badge = "👑 ADMIN" if user.is_admin else ""
        print(f"{user.id:3d} | {user.username:20s} | {user.full_name:25s} | {admin_badge}")
    print("="*80 + "\n")

def show_user_permissions(user_id):
    """عرض صلاحيات المستخدم الحالية"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ المستخدم {user_id} غير موجود")
        return
    
    print("\n" + "="*80)
    print(f"👤 صلاحيات المستخدم: {user.full_name} ({user.username})")
    print("="*80)
    
    permissions = {
        "الصلاحيات الأساسية": {
            "can_manage_workers": "إدارة العمال",
            "can_manage_inventory": "إدارة المخزون",
            "can_manage_production": "إدارة الإنتاج",
            "can_manage_sales": "إدارة المبيعات",
            "can_manage_accounting": "إدارة المحاسبة",
            "can_manage_reports": "عرض التقارير",
            "can_edit": "تعديل البيانات",
            "can_delete": "حذف البيانات",
        },
        "الصلاحيات المتقدمة للإنتاج": {
            "can_manage_crop_health": "إدارة صحة المحاصيل",
            "can_manage_production_batches": "إدارة دفعات الإنتاج",
            "can_manage_production_costs": "إدارة تكاليف الإنتاج",
            "can_manage_production_stages": "إدارة مراحل الإنتاج",
            "can_view_analytics": "عرض التحليلات",
        }
    }
    
    for section, perms in permissions.items():
        print(f"\n{section}:")
        for attr, label in perms.items():
            status = "✅" if getattr(user, attr) else "❌"
            print(f"  {status} {label}")
    
    print("="*80 + "\n")

def grant_permission(user_id, permission):
    """منح صلاحية للمستخدم"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ المستخدم {user_id} غير موجود")
        return False
    
    if hasattr(user, permission):
        setattr(user, permission, True)
        db.session.commit()
        print(f"✅ تم منح صلاحية '{permission}' للمستخدم {user.full_name}")
        return True
    else:
        print(f"❌ الصلاحية '{permission}' غير موجودة")
        return False

def revoke_permission(user_id, permission):
    """سحب صلاحية من المستخدم"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ المستخدم {user_id} غير موجود")
        return False
    
    if hasattr(user, permission):
        setattr(user, permission, False)
        db.session.commit()
        print(f"✅ تم سحب صلاحية '{permission}' من المستخدم {user.full_name}")
        return True
    else:
        print(f"❌ الصلاحية '{permission}' غير موجودة")
        return False

def grant_all_production_permissions(user_id):
    """منح جميع صلاحيات الإنتاج المتقدمة للمستخدم"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ المستخدم {user_id} غير موجود")
        return
    
    production_perms = [
        "can_manage_crop_health",
        "can_manage_production_batches",
        "can_manage_production_costs",
        "can_manage_production_stages",
        "can_view_analytics"
    ]
    
    for perm in production_perms:
        setattr(user, perm, True)
    
    db.session.commit()
    print(f"✅ تم منح جميع صلاحيات الإنتاج المتقدمة للمستخدم {user.full_name}")

def main():
    with app.app_context():
        while True:
            print("\n" + "="*80)
            print("🔐 إدارة صلاحيات المستخدمين")
            print("="*80)
            print("1️⃣  عرض قائمة المستخدمين")
            print("2️⃣  عرض صلاحيات مستخدم")
            print("3️⃣  منح صلاحية للمستخدم")
            print("4️⃣  سحب صلاحية من المستخدم")
            print("5️⃣  منح جميع صلاحيات الإنتاج المتقدمة")
            print("6️⃣  خروج")
            print("="*80)
            
            choice = input("\nاختر خياراً (1-6): ").strip()
            
            if choice == '1':
                show_users()
            
            elif choice == '2':
                show_users()
                user_id = input("أدخل معرف المستخدم: ").strip()
                try:
                    show_user_permissions(int(user_id))
                except ValueError:
                    print("❌ معرف غير صحيح")
            
            elif choice == '3':
                show_users()
                user_id = input("أدخل معرف المستخدم: ").strip()
                print("\nالصلاحيات المتاحة:")
                print("  - can_manage_workers (إدارة العمال)")
                print("  - can_manage_inventory (إدارة المخزون)")
                print("  - can_manage_production (إدارة الإنتاج)")
                print("  - can_manage_sales (إدارة المبيعات)")
                print("  - can_manage_accounting (إدارة المحاسبة)")
                print("  - can_manage_reports (عرض التقارير)")
                print("  - can_manage_crop_health (إدارة صحة المحاصيل)")
                print("  - can_manage_production_batches (إدارة دفعات الإنتاج)")
                print("  - can_manage_production_costs (إدارة تكاليف الإنتاج)")
                print("  - can_manage_production_stages (إدارة مراحل الإنتاج)")
                print("  - can_view_analytics (عرض التحليلات)")
                print("  - can_edit (تعديل البيانات)")
                print("  - can_delete (حذف البيانات)")
                permission = input("أدخل اسم الصلاحية: ").strip()
                try:
                    grant_permission(int(user_id), permission)
                except ValueError:
                    print("❌ معرف غير صحيح")
            
            elif choice == '4':
                show_users()
                user_id = input("أدخل معرف المستخدم: ").strip()
                print("\nالصلاحيات المتاحة:")
                print("  - can_manage_workers")
                print("  - can_manage_inventory")
                print("  - can_manage_production")
                print("  - can_manage_sales")
                print("  - can_manage_accounting")
                print("  - can_manage_reports")
                print("  - can_manage_crop_health")
                print("  - can_manage_production_batches")
                print("  - can_manage_production_costs")
                print("  - can_manage_production_stages")
                print("  - can_view_analytics")
                print("  - can_edit")
                print("  - can_delete")
                permission = input("أدخل اسم الصلاحية: ").strip()
                try:
                    revoke_permission(int(user_id), permission)
                except ValueError:
                    print("❌ معرف غير صحيح")
            
            elif choice == '5':
                show_users()
                user_id = input("أدخل معرف المستخدم: ").strip()
                try:
                    grant_all_production_permissions(int(user_id))
                except ValueError:
                    print("❌ معرف غير صحيح")
            
            elif choice == '6':
                print("👋 وداعاً!")
                break
            
            else:
                print("❌ خيار غير صحيح")

if __name__ == '__main__':
    main()
