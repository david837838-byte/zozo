from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """تسجيل الدخول"""
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('حسابك معطل. يرجى التواصل مع الإدارة.', 'danger')
                return redirect(url_for('auth.login'))
            
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home.index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    """تسجيل الخروج"""
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """تغيير كلمة المرور الشخصية"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # التحقق من كلمة المرور الحالية
        if not current_user.check_password(current_password):
            flash('كلمة المرور الحالية غير صحيحة', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # التحقق من أن كلمة المرور الجديدة والتأكيد متطابقة
        if new_password != confirm_password:
            flash('كلمة المرور الجديدة والتأكيد غير متطابقة', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # التحقق من طول كلمة المرور
        if len(new_password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # تحديث كلمة المرور
        current_user.set_password(new_password)
        db.session.commit()
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('home.index'))
    
    return render_template('auth/change_password.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """تسجيل مستخدم جديد (للأدمين فقط)"""
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('home.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('auth.register'))
        
        # Create new user
        user = User(username=username, email=email, full_name=full_name)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'تم إنشاء حساب {full_name} بنجاح', 'success')
        return redirect(url_for('settings.users'))
    
    return render_template('auth/register.html')
