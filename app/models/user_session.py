from datetime import datetime

from app import db


class UserSession(db.Model):
    """Track authenticated user devices/sessions."""

    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    session_token = db.Column(db.String(128), nullable=False, unique=True, index=True)
    device_type = db.Column(db.String(20), nullable=False, default="Unknown")
    device_name = db.Column(db.String(80), nullable=False, default="Unknown device")
    operating_system = db.Column(db.String(80), nullable=True)
    browser = db.Column(db.String(80), nullable=True)

    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    login_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    logged_out_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    user = db.relationship("User", lazy="joined")
    account = db.relationship("Account", lazy="joined")

    def __repr__(self):
        return f"<UserSession user={self.user_id} device={self.device_name}>"
