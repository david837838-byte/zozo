from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from datetime import datetime

class User(UserMixin, db.Model):
    """نموذج المستخدم"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Roles and permissions
    can_manage_workers = db.Column(db.Boolean, default=False)
    can_manage_inventory = db.Column(db.Boolean, default=False)
    can_manage_production = db.Column(db.Boolean, default=False)
    can_manage_sales = db.Column(db.Boolean, default=False)
    can_manage_accounting = db.Column(db.Boolean, default=False)
    can_manage_reports = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    
    # Advanced production permissions
    can_manage_crop_health = db.Column(db.Boolean, default=False)
    can_manage_production_batches = db.Column(db.Boolean, default=False)
    can_manage_production_costs = db.Column(db.Boolean, default=False)
    can_manage_production_stages = db.Column(db.Boolean, default=False)
    can_view_analytics = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        """تعيين كلمة المرور المشفرة"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """التحقق من كلمة المرور"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

@login_manager.user_loader
def load_user(user_id):
    """تحميل المستخدم من معرفه"""
    return User.query.get(int(user_id))
