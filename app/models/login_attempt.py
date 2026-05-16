from datetime import datetime, timedelta

from app import db


class LoginAttempt(db.Model):
    """Track failed login attempts and temporary lockout state."""

    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False, index=True)
    ip_address = db.Column(db.String(64), nullable=False, index=True)
    failure_count = db.Column(db.Integer, nullable=False, default=0)
    blocked_until = db.Column(db.DateTime, nullable=True, index=True)
    last_attempt_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint("username", "ip_address", name="uq_login_attempt_username_ip"),
    )

    def is_blocked(self, now=None):
        now = now or datetime.utcnow()
        return bool(self.blocked_until and self.blocked_until > now)

    def reset(self):
        self.failure_count = 0
        self.blocked_until = None
        self.last_attempt_at = datetime.utcnow()

    def apply_failure(
        self,
        *,
        threshold=7,
        base_minutes=5,
        escalation_every=3,
        max_minutes=120,
        now=None,
    ):
        """Register a failed attempt and return lockout minutes (0 if not blocked)."""
        now = now or datetime.utcnow()
        self.failure_count = int(self.failure_count or 0) + 1
        self.last_attempt_at = now

        if self.failure_count < threshold:
            self.blocked_until = None
            return 0

        escalation_level = max(0, (self.failure_count - threshold) // max(1, escalation_every))
        lock_minutes = min(base_minutes * (2**escalation_level), max_minutes)
        self.blocked_until = now + timedelta(minutes=lock_minutes)
        return lock_minutes
