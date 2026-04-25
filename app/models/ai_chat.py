from datetime import datetime

from app import db


class AIConversation(db.Model):
    """Stored AI chat session."""

    __tablename__ = "ai_conversation"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False, default="محادثة جديدة")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    messages = db.relationship(
        "AIConversationMessage",
        backref="conversation",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="AIConversationMessage.created_at.asc(), AIConversationMessage.id.asc()",
    )

    def __repr__(self):
        return f"<AIConversation {self.id}>"


class AIConversationMessage(db.Model):
    """Stored message for a conversation."""

    __tablename__ = "ai_conversation_message"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("ai_conversation.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # user | assistant
    text = db.Column(db.Text, nullable=False)
    backend = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AIConversationMessage {self.id} {self.role}>"
