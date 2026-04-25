import json
import os
import re
import base64
from datetime import date, datetime, timedelta
from urllib import error, parse, request as urlrequest

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models.app_setting import AppSetting
from app.models.ai_chat import AIConversation, AIConversationMessage
from app.models.crop import CropConsumption, CropHealth
from app.models.inventory import GeneralConsumption, InventoryItem

bp = Blueprint("ai_assistant", __name__, url_prefix="/ai")

_HISTORY_SESSION_KEY = "ai_assistant_history"
_ACTIVE_CONVERSATION_SESSION_KEY = "ai_assistant_active_conversation_id"
_MAX_HISTORY_ENTRIES = 16
_MAX_MESSAGE_LENGTH = 2500
_MAX_UPLOAD_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_UPLOAD_MIME_PREFIX = "image/"

_MEDICINE_KEYWORDS = (
    "دواء",
    "ادوية",
    "أدوية",
    "مبيد",
    "مبيدات",
    "علاج",
    "رش",
    "مادة فعالة",
    "pesticide",
    "medicine",
    "fungicide",
    "insecticide",
    "herbicide",
)

_DISEASE_KEYWORDS = (
    "مرض",
    "امراض",
    "أمراض",
    "آفة",
    "افات",
    "حشرة",
    "فطر",
    "فيروس",
    "بكتيريا",
    "ذبول",
    "اصفرار",
    "بقع",
    "تعفن",
)

_ANALYSIS_KEYWORDS = (
    "تحليل",
    "تحليلات",
    "ملخص",
    "تقرير",
    "اتجاه",
    "مؤشر",
    "analysis",
    "report",
    "summary",
)

_CRITICAL_STATUS_VALUES = {"حرجة", "حرجه", "critical", "severe"}

_MEDICINE_TYPE_CATALOG = [
    {
        "id": "fungicide",
        "title": "مبيد فطري",
        "aliases": ("فطري", "فطريات", "بياض", "عفن", "fungicide"),
        "benefit": "يستخدم لمكافحة الأمراض الفطرية مثل البياض الدقيقي واللفحات والأعفان.",
        "when": "عند ظهور بقع فطرية أو في برنامج وقائي حسب توصية فنية.",
    },
    {
        "id": "insecticide",
        "title": "مبيد حشري",
        "aliases": ("حشري", "حشرات", "من", "ذبابة", "thrips", "insecticide"),
        "benefit": "يقلل ضغط الحشرات الثاقبة أو القارضة مثل المن والذبابة البيضاء والتربس.",
        "when": "عند تجاوز الحد الاقتصادي للإصابة وبعد الفحص الحقلي.",
    },
    {
        "id": "acaricide",
        "title": "مبيد أكاروسي",
        "aliases": ("اكاروسي", "أكاروسي", "عنكبوت", "حلم", "mite", "acaricide"),
        "benefit": "مخصص لمكافحة الأكاروس/العناكب الدقيقة التي تسبب تبقعات واصفرار.",
        "when": "عند وجود أعراض شبكية أو زيادة أعداد الأكاروس في الورقة.",
    },
    {
        "id": "herbicide",
        "title": "مبيد أعشاب",
        "aliases": ("اعشاب", "أعشاب", "حشائش", "عشب", "herbicide"),
        "benefit": "يستخدم للسيطرة على الحشائش المنافسة للمحصول على الماء والغذاء.",
        "when": "قبل الإنبات أو بعده حسب نوع المحصول ونوع الحشائش.",
    },
    {
        "id": "bactericide",
        "title": "مبيد/مضاد بكتيري",
        "aliases": ("بكتيري", "بكتيريا", "bactericide"),
        "benefit": "يستخدم لتقليل شدة الإصابات البكتيرية في الأوراق والثمار.",
        "when": "عند تأكيد أعراض بكتيرية مع إدارة رطوبة وتهوية جيدة.",
    },
    {
        "id": "nematicide",
        "title": "مبيد نيماتودي",
        "aliases": ("نيماتودا", "نيماتودي", "nematicide"),
        "benefit": "يحد من أضرار نيماتودا الجذور التي تسبب ضعف النمو والذبول.",
        "when": "عند ثبوت إصابة بالتربة أو الجذور ضمن برنامج متكامل.",
    },
    {
        "id": "foliar_nutrition",
        "title": "تغذية ورقية/محفز",
        "aliases": ("سماد ورقي", "تغذيه", "تغذية", "كالسيوم", "بورون", "محفز", "منشط"),
        "benefit": "يرفع كفاءة التغذية ويعالج بعض أعراض النقص الغذائي.",
        "when": "عند ظهور أعراض نقص غذائي أو في مراحل حرجة من النمو.",
    },
]

_DISEASE_LIBRARY = [
    {
        "name": "البياض الدقيقي",
        "aliases": ("بياض دقيقي", "powdery mildew"),
        "signs": "طبقة بيضاء مسحوقية على الأوراق مع ضعف تدريجي.",
        "type_ids": ("fungicide",),
    },
    {
        "name": "اللفحة/الندوة",
        "aliases": ("لفحة", "ندوة", "blight"),
        "signs": "بقع بنية غير منتظمة وقد تمتد بسرعة مع رطوبة عالية.",
        "type_ids": ("fungicide",),
    },
    {
        "name": "أعفان الجذور",
        "aliases": ("تعفن جذور", "اعفان جذور", "root rot"),
        "signs": "ذبول رغم توفر ماء مع اسوداد/ضعف في المجموع الجذري.",
        "type_ids": ("fungicide", "nematicide"),
    },
    {
        "name": "ذبابة بيضاء/من",
        "aliases": ("ذبابة بيضاء", "من", "aphid", "whitefly"),
        "signs": "التفاف أوراق، اصفرار، إفرازات عسلية ونمو فطريات سطحية.",
        "type_ids": ("insecticide",),
    },
    {
        "name": "أكاروس/عنكبوت أحمر",
        "aliases": ("عنكبوت", "أكاروس", "اكاروس", "mite"),
        "signs": "تبقعات دقيقة، اصفرار، ومظهر شبكي أسفل الورقة.",
        "type_ids": ("acaricide",),
    },
]

_SYMPTOM_RULES = [
    {
        "aliases": ("ذبول", "wilting"),
        "likely": ["إجهاد مائي", "أعفان جذور", "انسداد أوعية بسبب ذبول فطري"],
        "type_ids": ("fungicide", "nematicide"),
        "actions": [
            "افحص رطوبة التربة حول الجذور قبل أي رش.",
            "استبعد النباتات شديدة التدهور من المساحة الرئيسية.",
            "حسن الصرف وقلل التغريق بين الريات.",
        ],
    },
    {
        "aliases": ("اصفرار", "yellow", "chlorosis"),
        "likely": ["نقص غذائي (حديد/نيتروجين)", "إجهاد جذور", "بداية إصابة حشرية"],
        "type_ids": ("foliar_nutrition", "insecticide"),
        "actions": [
            "افحص pH التربة والماء إن أمكن.",
            "ابدأ بتغذية ورقية متوازنة بجرعة بطاقة المنتج.",
            "افحص أسفل الورقة لاستبعاد الذبابة البيضاء أو المن.",
        ],
    },
    {
        "aliases": ("بقع", "تبقع", "spot"),
        "likely": ["مرض فطري ورقي", "لفحات مبكرة", "إجهاد بيئي"],
        "type_ids": ("fungicide",),
        "actions": [
            "أزل الأوراق الأكثر إصابة لتقليل مصدر العدوى.",
            "حسن التهوية وتجنب البلل الليلي للأوراق.",
            "تابع تطور البقع بعد 72 ساعة.",
        ],
    },
    {
        "aliases": ("تعفن", "عفن", "rot"),
        "likely": ["عدوى فطرية", "رطوبة زائدة", "ملامسة ثمار للتربة"],
        "type_ids": ("fungicide",),
        "actions": [
            "قلل الرطوبة الحرة ورفع التهوية.",
            "اعزل الثمار أو الأنسجة المتعفنة فورًا.",
            "نظف أدوات القص والتقليم قبل الاستخدام التالي.",
        ],
    },
]

_GENERAL_TOPICS = [
    {
        "aliases": ("ري", "ماء", "عطش", "irrigation"),
        "advice": [
            "اجعل الري حسب رطوبة الجذور وليس حسب وقت ثابت فقط.",
            "الري الصباحي أفضل لتقليل رطوبة ليلية على الأوراق.",
            "تجنب التذبذب الحاد بين الجفاف ثم التغريق لأنه يرفع الإجهاد.",
        ],
    },
    {
        "aliases": ("تسميد", "سماد", "تغذية", "fertilizer", "npk"),
        "advice": [
            "ابدأ بتحليل التربة/الماء إن متاح قبل رفع الجرعات.",
            "قسّم الجرعة على دفعات صغيرة لتحسين الامتصاص.",
            "وازن بين العناصر الكبرى والصغرى لتجنب نقص ثانوي.",
        ],
    },
    {
        "aliases": ("تربة", "ملوحة", "ph", "soil"),
        "advice": [
            "راقب pH والملوحة بشكل دوري خاصة مع مياه قاسية.",
            "حسن المادة العضوية لرفع نشاط الجذور.",
            "استخدم غسيل أملاح تدريجي عند ارتفاع EC.",
        ],
    },
    {
        "aliases": ("حر", "حرارة", "صقيع", "برد", "heat", "frost"),
        "advice": [
            "في موجات الحر: خفف إجهاد النبات بالري المبكر والتظليل النسبي.",
            "في البرد: قلل الري الليلي وتجنب الرش قبل الصقيع.",
            "راقب الأنسجة الحديثة لأنها الأكثر تأثرا بالتقلبات.",
        ],
    },
]

_TYPE_BY_ID = {item["id"]: item for item in _MEDICINE_TYPE_CATALOG}


def _normalize_text(value):
    text = (value or "").strip().lower()
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _tokenize(value):
    return re.findall(r"[a-z0-9\u0600-\u06ff]+", _normalize_text(value))


def _contains_any(text, keywords):
    normalized = _normalize_text(text)
    for keyword in keywords:
        if _normalize_text(keyword) in normalized:
            return True
    return False


def _find_catalog_types(text):
    normalized = _normalize_text(text)
    matched = []
    for item in _MEDICINE_TYPE_CATALOG:
        for alias in item["aliases"]:
            if _normalize_text(alias) in normalized:
                matched.append(item)
                break
    return matched


def _infer_medicine_type(text):
    matched = _find_catalog_types(text)
    if matched:
        return matched[0]
    return None


def _is_medicine_category(category):
    return _contains_any(category, _MEDICINE_KEYWORDS)


def _legacy_ai_access():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_manage_production", False)
        or getattr(current_user, "can_manage_inventory", False)
        or getattr(current_user, "can_manage_reports", False)
    )


def _can_use_ai_assistant():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_use_ai_assistant", False)
        or _legacy_ai_access()
    )


def _can_view_ai_history():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_view_ai_history", False)
        or _can_use_ai_assistant()
    )


def _can_use_ai_upload():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_use_ai_upload", False)
        or _can_use_ai_assistant()
    )


def _can_use_ai_voice():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_use_ai_voice", False)
        or _can_use_ai_assistant()
    )


def _can_view_ai_reports():
    return bool(
        current_user.is_admin
        or getattr(current_user, "can_view_ai_reports", False)
        or getattr(current_user, "can_manage_reports", False)
    )


def _has_ai_access():
    return _can_use_ai_assistant()


def _guard_access():
    if _has_ai_access():
        return None
    flash("ليس لديك صلاحية الوصول إلى المساعد الذكي", "danger")
    return redirect(url_for("home.index"))


def _guard_history_access():
    if _can_view_ai_history():
        return None
    flash("ليس لديك صلاحية عرض سجلات المحادثة.", "danger")
    return redirect(url_for("home.index"))


def _guard_reports_access():
    if _can_view_ai_reports():
        return None
    flash("ليس لديك صلاحية عرض تقارير الذكاء الاصطناعي.", "danger")
    return redirect(url_for("home.index"))


def _account_setting_key(base_key):
    account_id = getattr(current_user, "account_id", None)
    if account_id:
        return f"account:{account_id}:{base_key}"
    return base_key


def _setting_get_raw(base_key):
    return (AppSetting.get_value(_account_setting_key(base_key), None) or "").strip()


def _effective_remote_config():
    provider = (_setting_get_raw("ai_provider") or os.environ.get("AI_PROVIDER") or "auto").strip().lower()
    if provider not in {"auto", "gemini", "openai", "local"}:
        provider = "auto"

    gemini_key = (
        _setting_get_raw("gemini_api_key")
        or current_app.config.get("GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    openai_key = (
        _setting_get_raw("openai_api_key")
        or current_app.config.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()

    gemini_model = (
        _setting_get_raw("gemini_model")
        or current_app.config.get("GEMINI_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or "gemini-2.5-flash"
    ).strip()
    openai_model = (
        _setting_get_raw("openai_model")
        or current_app.config.get("OPENAI_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-5.4-mini"
    ).strip()

    return {
        "provider": provider,
        "gemini_key": gemini_key,
        "openai_key": openai_key,
        "gemini_model": gemini_model,
        "openai_model": openai_model,
    }


def _describe_ai_mode(config):
    provider = config.get("provider")
    has_gemini = bool(config.get("gemini_key"))
    has_openai = bool(config.get("openai_key"))

    if provider == "local":
        return "Local expert mode"
    if provider == "gemini":
        return f"Gemini ({config.get('gemini_model')})" if has_gemini else "Gemini selected (missing API key)"
    if provider == "openai":
        return f"OpenAI ({config.get('openai_model')})" if has_openai else "OpenAI selected (missing API key)"

    if has_gemini:
        return f"Auto: Gemini ({config.get('gemini_model')})"
    if has_openai:
        return f"Auto: OpenAI ({config.get('openai_model')})"
    return "Local expert mode"


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _conversation_title_from_question(question):
    text = " ".join((question or "").strip().split())
    if not text:
        return "محادثة جديدة"
    return text[:120]


def _active_conversation_id():
    return _safe_int(session.get(_ACTIVE_CONVERSATION_SESSION_KEY))


def _set_active_conversation_id(conversation_id):
    session[_ACTIVE_CONVERSATION_SESSION_KEY] = int(conversation_id)
    session.modified = True


def _clear_active_conversation():
    session.pop(_ACTIVE_CONVERSATION_SESSION_KEY, None)
    session.modified = True


def _load_history_from_conversation(conversation_id):
    if not conversation_id:
        return []

    messages = (
        AIConversationMessage.query.filter_by(conversation_id=conversation_id)
        .order_by(AIConversationMessage.created_at.asc(), AIConversationMessage.id.asc())
        .all()
    )

    history = []
    for msg in messages:
        role = (msg.role or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = (msg.text or "").strip()
        if not text:
            continue
        history.append(
            {
                "role": role,
                "text": text[:_MAX_MESSAGE_LENGTH],
                "backend": (msg.backend or "").strip(),
            }
        )
    return history


def _read_history():
    conversation_id = _active_conversation_id()
    if conversation_id:
        db_history = _load_history_from_conversation(conversation_id)
        if db_history:
            session[_HISTORY_SESSION_KEY] = db_history[-_MAX_HISTORY_ENTRIES:]
            session.modified = True
            return db_history

    raw = session.get(_HISTORY_SESSION_KEY, [])
    if not isinstance(raw, list):
        return []

    history = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        role = (entry.get("role") or "").strip().lower()
        text = str(entry.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        history.append(
            {
                "role": role,
                "text": text[:_MAX_MESSAGE_LENGTH],
                "backend": (entry.get("backend") or "").strip(),
            }
        )
    return history[-_MAX_HISTORY_ENTRIES:]


def _save_history(history):
    session[_HISTORY_SESSION_KEY] = history[-_MAX_HISTORY_ENTRIES:]
    session.modified = True


def _current_account_id():
    return getattr(current_user, "account_id", None)


def _get_active_conversation():
    conversation_id = _active_conversation_id()
    if not conversation_id:
        return None
    conversation = AIConversation.query.filter_by(id=conversation_id).first()
    if not conversation:
        _clear_active_conversation()
        return None
    return conversation


def _create_conversation_from_question(question):
    conversation = AIConversation(
        account_id=_current_account_id(),
        user_id=getattr(current_user, "id", None),
        title=_conversation_title_from_question(question),
    )
    db.session.add(conversation)
    db.session.flush()
    _set_active_conversation_id(conversation.id)
    return conversation


def _append_messages_to_conversation(conversation, user_question, answer, backend):
    account_id = _current_account_id()
    now = datetime.utcnow()

    db.session.add(
        AIConversationMessage(
            account_id=account_id,
            conversation_id=conversation.id,
            role="user",
            text=user_question[:_MAX_MESSAGE_LENGTH],
            backend="",
            created_at=now,
        )
    )
    db.session.add(
        AIConversationMessage(
            account_id=account_id,
            conversation_id=conversation.id,
            role="assistant",
            text=answer[:_MAX_MESSAGE_LENGTH],
            backend=(backend or "")[:50],
            created_at=now,
        )
    )
    conversation.updated_at = now
    if not (conversation.title or "").strip():
        conversation.title = _conversation_title_from_question(user_question)


def _collect_ai_analytics():
    today = date.today()
    health_window_days = 90
    usage_window_days = 30

    health_from_date = today - timedelta(days=health_window_days)
    usage_from_date = today - timedelta(days=usage_window_days)

    health_rows = (
        CropHealth.query.filter(CropHealth.health_date >= health_from_date)
        .order_by(CropHealth.health_date.desc())
        .all()
    )

    critical_statuses = {_normalize_text(value) for value in _CRITICAL_STATUS_VALUES}
    critical_cases = 0
    for record in health_rows:
        severity = float(record.severity_percentage or 0)
        status = _normalize_text(record.health_status)
        if severity >= 60 or status in critical_statuses:
            critical_cases += 1

    top_disease_rows = (
        db.session.query(CropHealth.disease_name, func.count(CropHealth.id))
        .filter(
            CropHealth.health_date >= health_from_date,
            CropHealth.disease_name.isnot(None),
            CropHealth.disease_name != "",
        )
        .group_by(CropHealth.disease_name)
        .order_by(func.count(CropHealth.id).desc())
        .limit(6)
        .all()
    )

    all_inventory_items = InventoryItem.query.order_by(InventoryItem.name.asc()).all()
    medicine_rows = []
    for item in all_inventory_items:
        if not _is_medicine_category(item.category):
            continue
        inferred = _infer_medicine_type(
            " ".join(
                (
                    item.name or "",
                    item.category or "",
                    item.active_ingredient or "",
                    item.common_usage or "",
                    item.notes or "",
                )
            )
        )
        medicine_rows.append(
            {
                "id": item.id,
                "name": item.name,
                "category": item.category or "",
                "quantity": float(item.quantity or 0),
                "unit": item.unit or "",
                "active_ingredient": (item.active_ingredient or "").strip(),
                "common_usage": (item.common_usage or "").strip(),
                "safety_notes": (item.safety_notes or "").strip(),
                "expiry_date": item.expiry_date.strftime("%Y-%m-%d") if item.expiry_date else "",
                "notes": (item.notes or "").strip(),
                "type_id": inferred["id"] if inferred else "unknown",
                "type_title": inferred["title"] if inferred else "غير مصنف",
            }
        )

    out_of_stock_medicines = [item for item in medicine_rows if item["quantity"] <= 0]
    low_stock_medicines = [item for item in medicine_rows if 0 < item["quantity"] <= 10]
    available_medicines = [item for item in medicine_rows if item["quantity"] > 0]
    expiring_soon_medicines = []
    expiry_limit = today + timedelta(days=30)
    for item in all_inventory_items:
        if not _is_medicine_category(item.category):
            continue
        if not item.expiry_date:
            continue
        if item.expiry_date <= expiry_limit:
            expiring_soon_medicines.append(
                {
                    "name": item.name,
                    "expiry_date": item.expiry_date.strftime("%Y-%m-%d"),
                    "days_left": (item.expiry_date - today).days,
                    "quantity": float(item.quantity or 0),
                    "unit": item.unit or "",
                }
            )

    item_ids = [item.id for item in all_inventory_items if _is_medicine_category(item.category)]
    usage_by_medicine = {}
    if item_ids:
        crop_usage_rows = (
            db.session.query(InventoryItem.name, func.coalesce(func.sum(CropConsumption.quantity_used), 0))
            .join(CropConsumption, CropConsumption.inventory_item_id == InventoryItem.id)
            .filter(
                InventoryItem.id.in_(item_ids),
                CropConsumption.consumption_date >= usage_from_date,
            )
            .group_by(InventoryItem.name)
            .all()
        )
        general_usage_rows = (
            db.session.query(InventoryItem.name, func.coalesce(func.sum(GeneralConsumption.quantity_used), 0))
            .join(GeneralConsumption, GeneralConsumption.inventory_item_id == InventoryItem.id)
            .filter(
                InventoryItem.id.in_(item_ids),
                GeneralConsumption.consumption_date >= usage_from_date,
            )
            .group_by(InventoryItem.name)
            .all()
        )

        for item_name, quantity in crop_usage_rows + general_usage_rows:
            key = item_name or "غير محدد"
            usage_by_medicine[key] = usage_by_medicine.get(key, 0.0) + float(quantity or 0)

    top_medicine_usage = sorted(usage_by_medicine.items(), key=lambda row: row[1], reverse=True)[:6]

    latest_health_records = []
    for record in health_rows[:10]:
        if not (record.disease_name or record.pest_name):
            continue
        latest_health_records.append(
            {
                "crop_name": record.crop.name if record.crop else "غير معروف",
                "disease_name": (record.disease_name or "").strip(),
                "pest_name": (record.pest_name or "").strip(),
                "severity": float(record.severity_percentage or 0),
                "status": record.health_status or "",
                "date": record.health_date.strftime("%Y-%m-%d") if record.health_date else "-",
            }
        )

    weekly_from_date = today - timedelta(days=6)
    weekly_health_rows = [record for record in health_rows if record.health_date and record.health_date >= weekly_from_date]
    weekly_critical_cases = 0
    for record in weekly_health_rows:
        severity = float(record.severity_percentage or 0)
        status = _normalize_text(record.health_status)
        if severity >= 60 or status in critical_statuses:
            weekly_critical_cases += 1

    weekly_top_disease_rows = (
        db.session.query(CropHealth.disease_name, func.count(CropHealth.id))
        .filter(
            CropHealth.health_date >= weekly_from_date,
            CropHealth.disease_name.isnot(None),
            CropHealth.disease_name != "",
        )
        .group_by(CropHealth.disease_name)
        .order_by(func.count(CropHealth.id).desc())
        .limit(5)
        .all()
    )

    auto_alerts = []
    if out_of_stock_medicines:
        for item in out_of_stock_medicines[:5]:
            auto_alerts.append(
                {
                    "level": "high",
                    "title": f"نفاد دواء: {item['name']}",
                    "details": "المخزون صفر، يفضل إنشاء طلب شراء أو توفير بديل.",
                }
            )
    if low_stock_medicines:
        for item in sorted(low_stock_medicines, key=lambda row: row["quantity"])[:5]:
            auto_alerts.append(
                {
                    "level": "medium",
                    "title": f"مخزون منخفض: {item['name']}",
                    "details": f"الكمية الحالية {item['quantity']} {item['unit']}.",
                }
            )
    if weekly_critical_cases > 0:
        auto_alerts.append(
            {
                "level": "high",
                "title": "حالات صحية حرجة هذا الأسبوع",
                "details": f"تم تسجيل {weekly_critical_cases} حالة حرجة خلال آخر 7 أيام.",
            }
        )
    if expiring_soon_medicines:
        for item in sorted(expiring_soon_medicines, key=lambda row: row["days_left"])[:4]:
            auto_alerts.append(
                {
                    "level": "medium",
                    "title": f"دواء قريب الانتهاء: {item['name']}",
                    "details": f"ينتهي بتاريخ {item['expiry_date']} (بعد {item['days_left']} يوم).",
                }
            )

    return {
        "health_window_days": health_window_days,
        "usage_window_days": usage_window_days,
        "total_health_cases": len(health_rows),
        "critical_cases": critical_cases,
        "top_diseases": [{"name": row[0], "count": int(row[1])} for row in top_disease_rows if row[0]],
        "medicine_count": len(medicine_rows),
        "out_of_stock_count": len(out_of_stock_medicines),
        "low_stock_count": len(low_stock_medicines),
        "expiring_soon_count": len(expiring_soon_medicines),
        "available_medicines": sorted(available_medicines, key=lambda item: item["quantity"], reverse=True)[:12],
        "low_stock_medicines": sorted(low_stock_medicines, key=lambda item: item["quantity"])[:12],
        "expiring_soon_medicines": sorted(expiring_soon_medicines, key=lambda item: item["days_left"])[:12],
        "top_medicine_usage": [
            {"name": row[0], "quantity": round(float(row[1]), 2)}
            for row in top_medicine_usage
        ],
        "latest_health_records": latest_health_records,
        "weekly_window_days": 7,
        "weekly_total_health_cases": len(weekly_health_rows),
        "weekly_critical_cases": weekly_critical_cases,
        "weekly_top_diseases": [
            {"name": row[0], "count": int(row[1])}
            for row in weekly_top_disease_rows
            if row[0]
        ],
        "auto_alerts": auto_alerts[:15],
        "medicine_items": medicine_rows,
    }


def _history_snippet(history):
    lines = []
    for entry in history[-4:]:
        role = "المستخدم" if entry.get("role") == "user" else "المساعد"
        lines.append(f"- {role}: {entry.get('text', '')[:250]}")
    return "\n".join(lines)


def _build_prompt(user_question, analytics, history, image_context=None):
    lines = [
        "أنت مساعد زراعي ذكي. أجب بالعربية الواضحة وبشكل عملي.",
        "لا تعطِ جرعات رقمية دقيقة للأدوية؛ اطلب دائما الرجوع لبطاقة المنتج المحلية.",
        "إذا سأل المستخدم عن نوع دواء فاشرح فائدته ومتى يستخدمه.",
        "إذا لم تتأكد من التشخيص فاذكر الاحتمالات وخطوات التأكد.",
        "",
        f"سؤال المستخدم: {user_question}",
        "",
        "سياق المحادثة الأخيرة:",
        _history_snippet(history) or "- لا يوجد",
        "",
        "بيانات المزرعة:",
        f"- سجلات الصحة (آخر {analytics['health_window_days']} يوم): {analytics['total_health_cases']}",
        f"- الحالات الحرجة: {analytics['critical_cases']}",
        f"- عدد الأدوية بالمخزون: {analytics['medicine_count']}",
        f"- الأدوية منخفضة/نافدة: {analytics['low_stock_count'] + analytics['out_of_stock_count']}",
    ]

    if image_context:
        lines.append("- المستخدم أرسل صورة. قدم تشخيصًا مبدئيًا ثم اطلب فحصًا حقليًا للتأكيد.")

    if analytics["top_diseases"]:
        lines.append("- أكثر المشاكل تكراراً:")
        for item in analytics["top_diseases"][:5]:
            lines.append(f"  * {item['name']}: {item['count']} حالة")

    if analytics["available_medicines"]:
        lines.append("- أمثلة من الأدوية المتاحة:")
        for item in analytics["available_medicines"][:6]:
            lines.append(f"  * {item['name']} ({item['quantity']} {item['unit']})")

    if analytics.get("auto_alerts"):
        lines.append("- تنبيهات تلقائية:")
        for alert in analytics["auto_alerts"][:4]:
            lines.append(f"  * {alert['title']}: {alert['details']}")

    lines.extend(
        [
            "",
            "نمط الإجابة:",
            "1) جواب مباشر على السؤال.",
            "2) خطوات تنفيذية قصيرة الآن.",
            "3) ماذا تراقب خلال 3-7 أيام.",
            "4) تنبيه مهني مختصر.",
        ]
    )
    return "\n".join(lines)


def _ask_gemini(prompt, api_key=None, model=None, image_context=None):
    api_key = (
        api_key
        or current_app.config.get("GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        return None, "no_api_key"

    model = model or current_app.config.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    query = parse.urlencode({"key": api_key})
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"

    parts = [{"text": prompt}]
    if image_context:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image_context["mime_type"],
                    "data": image_context["base64_data"],
                }
            }
        )

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.45,
            "maxOutputTokens": 1000,
        },
    }

    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlrequest.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError:
        return None, "http_error"
    except Exception:
        return None, "network_error"

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid_response"

    candidates = result.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text_parts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        answer = "\n".join(text_parts).strip()
        if answer:
            return answer, None

    return None, "empty_response"


def _extract_openai_output_text(payload):
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    collected = []
    for output_item in payload.get("output", []) or []:
        for part in output_item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            text_value = part.get("text")
            if isinstance(text_value, str) and text_value.strip():
                collected.append(text_value.strip())
                continue
            maybe_value = part.get("value")
            if isinstance(maybe_value, str) and maybe_value.strip():
                collected.append(maybe_value.strip())
    return "\n".join(collected).strip()


def _clean_assistant_output(text):
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_image_context_from_request():
    uploaded_image = request.files.get("image")
    if not uploaded_image or not uploaded_image.filename:
        return None, None, None

    if not _can_use_ai_upload():
        return None, "ليس لديك صلاحية رفع الصور للتحليل.", None

    mime_type = (uploaded_image.mimetype or "").strip().lower()
    if not mime_type.startswith(_ALLOWED_UPLOAD_MIME_PREFIX):
        return None, "يجب رفع ملف صورة صالح (PNG/JPG/WebP).", None

    try:
        raw = uploaded_image.read()
    except Exception:
        return None, "تعذر قراءة الصورة المرفوعة.", None

    if not raw:
        return None, "الصورة المرفوعة فارغة.", None

    if len(raw) > _MAX_UPLOAD_IMAGE_BYTES:
        max_mb = int(_MAX_UPLOAD_IMAGE_BYTES / (1024 * 1024))
        return None, f"حجم الصورة كبير جدا. الحد الأقصى {max_mb}MB.", None

    return {
        "mime_type": mime_type,
        "base64_data": base64.b64encode(raw).decode("ascii"),
    }, None, "تم إرفاق صورة للتحليل."


def _ask_openai(prompt, api_key=None, model=None, image_context=None):
    api_key = (api_key or current_app.config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None, "no_api_key"

    model = (model or current_app.config.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.4-mini").strip()
    endpoint = "https://api.openai.com/v1/responses"
    user_content = [{"type": "input_text", "text": prompt}]
    if image_context:
        user_content.append(
            {
                "type": "input_image",
                "image_url": f"data:{image_context['mime_type']};base64,{image_context['base64_data']}",
            }
        )

    payload = {
        "model": model,
        "input": [{"role": "user", "content": user_content}],
        "temperature": 0.45,
        "max_output_tokens": 1000,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urlrequest.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError:
        return None, "http_error"
    except Exception:
        return None, "network_error"

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid_response"

    answer = _extract_openai_output_text(result)
    if answer:
        return answer, None
    return None, "empty_response"


def _expand_question_with_context(user_question, history):
    short_followups = ("وماذا", "وماذا عن", "وهذا", "طيب", "طيب و", "هل ينفع", "هل يفيد")
    normalized = _normalize_text(user_question)
    is_short = len(_tokenize(user_question)) <= 4
    if not is_short:
        return user_question
    if not any(_normalize_text(prefix) in normalized for prefix in short_followups):
        return user_question

    previous_user = ""
    for entry in reversed(history):
        if entry.get("role") == "user" and entry.get("text"):
            previous_user = entry["text"]
            break

    if not previous_user:
        return user_question
    return f"{previous_user}\nمتابعة: {user_question}"


def _detect_intent(question):
    has_analysis = _contains_any(question, _ANALYSIS_KEYWORDS)
    has_disease = (
        _contains_any(question, _DISEASE_KEYWORDS)
        or bool(_find_disease_knowledge(question))
        or bool(_find_symptom_matches(question))
    )
    has_medicine = _contains_any(question, _MEDICINE_KEYWORDS) or bool(_find_catalog_types(question))
    asks_types = _contains_any(question, ("نوع", "انواع", "أنواع", "تصنيف", "فئات", "فرق بين"))
    asks_compare = _contains_any(question, ("قارن", "مقارنة", "فرق بين", "compare", "comparison"))
    asks_weekly_plan = _contains_any(
        question,
        (
            "خطة اسبوع",
            "خطة أسبوع",
            "برنامج اسبوع",
            "برنامج أسبوع",
            "خطة علاج",
            "جدول علاج",
            "weekly plan",
            "treatment plan",
        ),
    )
    asks_alerts = _contains_any(question, ("تنبيه", "تنبيهات", "انذار", "إنذار", "تحذير", "نواقص", "نفد"))
    asks_weekly_report = _contains_any(question, ("تقرير اسبوع", "تقرير أسبوع", "ملخص اسبوع", "weekly report"))
    asks_benefit = _contains_any(
        question,
        (
            "يفيد",
            "فوائد",
            "استخدام",
            "يستخدم",
            "وظيف",
            "ماذا يفعل",
            "benefit",
            "use",
            "help",
            "purpose",
            "for what",
            "what for",
        ),
    )

    if asks_weekly_report:
        return "weekly_report"
    if asks_compare and has_medicine:
        return "medicine_compare"
    if asks_weekly_plan:
        return "weekly_plan"
    if asks_alerts:
        return "alerts"
    if has_analysis:
        return "analysis"
    if has_medicine and asks_types:
        return "medicine_types"
    if has_disease:
        return "disease"
    if has_medicine or asks_benefit:
        return "medicine_usage"
    return "general"


def _match_inventory_medicines(question, analytics):
    normalized_question = _normalize_text(question)
    question_tokens = set(_tokenize(question))
    scored = []

    for item in analytics.get("medicine_items", []):
        item_name_norm = _normalize_text(item["name"])
        active_norm = _normalize_text(item.get("active_ingredient") or "")
        usage_norm = _normalize_text(item.get("common_usage") or "")
        notes_norm = _normalize_text(item.get("notes") or "")
        search_blob = " ".join(
            (
                item.get("name") or "",
                item.get("active_ingredient") or "",
                item.get("common_usage") or "",
                item.get("safety_notes") or "",
                item.get("notes") or "",
            )
        )
        item_tokens = set(_tokenize(search_blob))
        score = 0

        if item_name_norm and item_name_norm in normalized_question:
            score += 10
        if active_norm and active_norm in normalized_question:
            score += 8
        if usage_norm and usage_norm in normalized_question:
            score += 4
        if notes_norm and notes_norm in normalized_question:
            score += 2
        token_overlap = len(question_tokens.intersection(item_tokens))
        score += token_overlap

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda row: row[0], reverse=True)
    unique = []
    seen = set()
    for _, item in scored:
        key = _normalize_text(item["name"])
        if key in seen:
            continue
        unique.append(item)
        seen.add(key)
        if len(unique) >= 4:
            break
    return unique


def _find_disease_knowledge(question):
    normalized = _normalize_text(question)
    matches = []
    for disease in _DISEASE_LIBRARY:
        for alias in disease["aliases"]:
            if _normalize_text(alias) in normalized:
                matches.append(disease)
                break
    return matches


def _find_symptom_matches(question):
    normalized = _normalize_text(question)
    matches = []
    for rule in _SYMPTOM_RULES:
        for alias in rule["aliases"]:
            if _normalize_text(alias) in normalized:
                matches.append(rule)
                break
    return matches


def _find_general_topics(question):
    normalized = _normalize_text(question)
    matches = []
    for topic in _GENERAL_TOPICS:
        for alias in topic["aliases"]:
            if _normalize_text(alias) in normalized:
                matches.append(topic)
                break
    return matches


def _medicine_candidates_by_type(analytics, type_ids):
    if not type_ids:
        return []
    rows = []
    wanted = set(type_ids)
    for item in analytics.get("available_medicines", []):
        if item.get("type_id") in wanted:
            rows.append(item)
    return rows[:6]


def _build_medicine_types_answer(question, analytics):
    requested_types = _find_catalog_types(question)
    if not requested_types:
        requested_types = _MEDICINE_TYPE_CATALOG

    lines = ["أنواع الأدوية الزراعية وفائدة كل نوع:"]
    for item in requested_types:
        lines.append(f"1) {item['title']}: {item['benefit']}")
        lines.append(f"2) متى يستخدم: {item['when']}")

        stock_matches = _medicine_candidates_by_type(analytics, [item["id"]])
        if stock_matches:
            preview = ", ".join(
                f"{entry['name']} ({entry['quantity']} {entry['unit']})" for entry in stock_matches[:3]
            )
            lines.append(f"3) متوفر عندك بالمخزون: {preview}")
        else:
            lines.append("3) لا يوجد دواء مصنف من هذا النوع حاليا في المخزون.")

    lines.append("اختر النوع حسب سبب الإصابة الحقيقي وليس حسب الأعراض فقط.")
    lines.append("تنبيه مهني: الجرعة وفترة الأمان تؤخذ فقط من بطاقة المنتج المحلي.")
    return "\n".join(lines)


def _build_medicine_usage_answer(question, analytics):
    matched_items = _match_inventory_medicines(question, analytics)
    requested_types = _find_catalog_types(question)

    lines = []
    if matched_items:
        lines.append("تحليل الأدوية المذكورة في سؤالك:")
        for item in matched_items:
            lines.append(f"1) {item['name']}: يساعد غالبا ضمن فئة {item['type_title']}.")
            lines.append(f"2) الكمية المتاحة: {item['quantity']} {item['unit']}.")
            if item.get("active_ingredient"):
                lines.append(f"3) المادة الفعالة: {item['active_ingredient']}.")
            if item.get("common_usage"):
                lines.append(f"4) الاستخدام المسجل: {item['common_usage']}.")
            else:
                lines.append(
                    "4) الاستخدام العام: "
                    + _TYPE_BY_ID.get(item["type_id"], {}).get("benefit", "الرجاء مراجعة المادة الفعالة على الملصق.")
                )
            if item.get("safety_notes"):
                lines.append(f"5) الأمان: {item['safety_notes']}")
            if item.get("notes"):
                lines.append(f"6) ملاحظة مسجلة بالنظام: {item['notes']}")
    elif requested_types:
        lines.append("بناء على النوع الذي ذكرته:")
        for item in requested_types:
            lines.append(f"1) {item['title']}: {item['benefit']}")
            lines.append(f"2) يستخدم غالبا عندما: {item['when']}")
    else:
        lines.append("لإعطائك فائدة دقيقة لكل دواء، اكتب اسم المنتج أو المادة الفعالة.")
        lines.append("مثال: ما فائدة دواء [اسم المنتج]؟ أو ما فائدة مادة [اسم المادة الفعالة]؟")

    lines.append("تطبيق عملي: بدّل المجموعات الكيميائية بين الرشات لتقليل المقاومة.")
    lines.append("تنبيه مهني: لا تستخدم أي دواء قبل التأكد من التشخيص ومطابقة المحصول على الملصق.")
    return "\n".join(lines)


def _build_disease_answer(question, analytics):
    disease_matches = _find_disease_knowledge(question)
    symptom_matches = _find_symptom_matches(question)

    lines = ["تشخيص مبدئي بناء على سؤالك وبيانات المزرعة:"]

    recommended_type_ids = []
    if disease_matches:
        for disease in disease_matches[:2]:
            lines.append(f"1) احتمال: {disease['name']}.")
            lines.append(f"2) علامة شائعة: {disease['signs']}")
            recommended_type_ids.extend(disease["type_ids"])

    if symptom_matches:
        for rule in symptom_matches[:2]:
            lines.append("3) احتمالات مرتبطة بالأعراض: " + "، ".join(rule["likely"]))
            lines.append("4) خطوات الآن: " + " | ".join(rule["actions"]))
            recommended_type_ids.extend(rule["type_ids"])

    if not disease_matches and not symptom_matches:
        lines.append("1) الأعراض غير كافية لتشخيص دقيق.")
        lines.append("2) أعطني: اسم المحصول، عمره، شكل الإصابة، وهل بدأت من الأوراق أم الجذور.")

    if analytics.get("top_diseases"):
        common = ", ".join(f"{item['name']} ({item['count']})" for item in analytics["top_diseases"][:3])
        lines.append(f"3) أكثر مشكلات متكررة عندك مؤخرا: {common}")

    stock_suggestions = _medicine_candidates_by_type(analytics, recommended_type_ids)
    if stock_suggestions:
        preview = ", ".join(f"{item['name']} ({item['quantity']} {item['unit']})" for item in stock_suggestions[:4])
        lines.append(f"4) أدوية مناسبة مبدئيا ومتوفرة: {preview}")

    lines.append("متابعة 3-7 أيام: راقب توسع الإصابة، لون النمو الجديد، واستجابة النبات بعد أول إجراء.")
    lines.append("تنبيه مهني: تأكيد التشخيص الحقلي أولوية قبل اعتماد برنامج الرش النهائي.")
    return "\n".join(lines)


def _build_analysis_answer(analytics):
    lines = [
        "تحليل أداء الصحة والدواء في مزرعتك:",
        f"1) إجمالي سجلات الصحة آخر {analytics['health_window_days']} يوم: {analytics['total_health_cases']}.",
        f"2) الحالات الحرجة: {analytics['critical_cases']}.",
        f"3) إجمالي الأدوية المسجلة: {analytics['medicine_count']}.",
        f"4) منخفض/نافد: {analytics['low_stock_count'] + analytics['out_of_stock_count']}.",
    ]

    if analytics.get("top_diseases"):
        lines.append("5) أكثر الأمراض/الآفات تكرارا:")
        for item in analytics["top_diseases"][:4]:
            lines.append(f"1) {item['name']} - {item['count']} حالة")

    if analytics.get("top_medicine_usage"):
        lines.append(f"6) أعلى استهلاك دوائي آخر {analytics['usage_window_days']} يوم:")
        for item in analytics["top_medicine_usage"][:4]:
            lines.append(f"1) {item['name']} - {item['quantity']}")

    lines.append("إجراء مقترح: راجع الأمراض المتكررة واربطها بخطة وقاية أسبوعية ثابتة.")
    lines.append("تنبيه مهني: أي تعديل كبير في برنامج المكافحة يفضل أن يراجع مع مهندس زراعي.")
    return "\n".join(lines)


def _build_alerts_answer(analytics):
    alerts = analytics.get("auto_alerts") or []
    if not alerts:
        return (
            "لا توجد تنبيهات حرجة حاليا.\n"
            "مع ذلك يُنصح بمراجعة المخزون وصحة المحاصيل مرة أسبوعيا."
        )

    lines = ["التنبيهات الذكية الحالية:"]
    for idx, alert in enumerate(alerts[:10], start=1):
        lines.append(f"{idx}) {alert['title']}")
        lines.append(f"   - {alert['details']}")

    lines.append("أولوية التنفيذ: عالج التنبيهات عالية الخطورة أولا ثم المتوسطة.")
    return "\n".join(lines)


def _build_medicine_comparison_answer(question, analytics):
    matched_items = _match_inventory_medicines(question, analytics)
    if len(matched_items) >= 2:
        first = matched_items[0]
        second = matched_items[1]
        lines = [
            f"مقارنة بين {first['name']} و {second['name']}:",
            f"1) الفئة: {first['type_title']} مقابل {second['type_title']}.",
            f"2) المادة الفعالة: {(first.get('active_ingredient') or 'غير مسجلة')} مقابل {(second.get('active_ingredient') or 'غير مسجلة')}.",
            f"3) الاستخدام: {(first.get('common_usage') or 'غير مسجل')} مقابل {(second.get('common_usage') or 'غير مسجل')}.",
            f"4) التوفر: {first['quantity']} {first['unit']} مقابل {second['quantity']} {second['unit']}.",
            "أفضلية الاختيار تعتمد على التشخيص الحقيقي، مرحلة النبات، وسجل الرش السابق.",
            "تنبيه مهني: لا تخلط أو تبدل بين منتجين قبل مراجعة بطاقة كل منتج.",
        ]
        return "\n".join(lines)

    requested_types = _find_catalog_types(question)
    if len(requested_types) >= 2:
        first = requested_types[0]
        second = requested_types[1]
        return "\n".join(
            [
                f"مقارنة نوعية بين {first['title']} و {second['title']}:",
                f"1) {first['title']}: {first['benefit']}",
                f"2) {second['title']}: {second['benefit']}",
                f"3) التوقيت: {first['when']} | {second['when']}",
                "اختيار النوع الصحيح يكون حسب سبب المشكلة وليس عرضًا واحدًا فقط.",
            ]
        )

    return (
        "لعمل مقارنة دقيقة اكتب اسمين واضحين من الأدوية.\n"
        "مثال: قارن بين [اسم الدواء الأول] و [اسم الدواء الثاني]."
    )


def _build_weekly_plan_answer(question, analytics):
    disease_matches = _find_disease_knowledge(question)
    symptom_matches = _find_symptom_matches(question)
    type_ids = []
    for disease in disease_matches[:2]:
        type_ids.extend(disease["type_ids"])
    for rule in symptom_matches[:2]:
        type_ids.extend(rule["type_ids"])

    suggested = _medicine_candidates_by_type(analytics, type_ids)
    lines = [
        "خطة أسبوعية مبدئية (7 أيام):",
        "اليوم 1: فحص حقلي في 10 نقاط وتسجيل الصور والأعراض.",
        "اليوم 2: عزل النباتات الأشد تضررا وتحسين التهوية/الري.",
        "اليوم 3: تطبيق إجراء علاجي مناسب حسب التشخيص المؤكد.",
        "اليوم 4: متابعة الاستجابة وقياس تراجع الأعراض.",
        "اليوم 5: ضبط تغذية داعمة وتقليل الإجهاد.",
        "اليوم 6: فحص إصابات جديدة وتحديث السجل.",
        "اليوم 7: تقييم النتيجة ووضع قرار الأسبوع التالي.",
    ]
    if suggested:
        lines.append(
            "أدوية متوفرة قد تدخل في الخطة: "
            + ", ".join(f"{item['name']} ({item['quantity']} {item['unit']})" for item in suggested[:5])
        )
    lines.append("تنبيه مهني: الجرعات وفترة الأمان تؤخذ حصرا من بطاقة المنتج المحلي.")
    return "\n".join(lines)


def _build_weekly_report_answer(analytics):
    lines = [
        "التقرير الأسبوعي الذكي:",
        f"1) سجلات الصحة خلال 7 أيام: {analytics.get('weekly_total_health_cases', 0)}.",
        f"2) الحالات الحرجة خلال 7 أيام: {analytics.get('weekly_critical_cases', 0)}.",
        f"3) تنبيهات المخزون الحالية: {analytics.get('low_stock_count', 0) + analytics.get('out_of_stock_count', 0)}.",
        f"4) أدوية قريبة الانتهاء (30 يوم): {analytics.get('expiring_soon_count', 0)}.",
    ]
    weekly_top = analytics.get("weekly_top_diseases") or []
    if weekly_top:
        lines.append("5) أكثر المشاكل هذا الأسبوع:")
        for item in weekly_top[:4]:
            lines.append(f"   - {item['name']} ({item['count']})")

    lines.append("توصية: اعمل اجتماع مراجعة أسبوعي قصير لتحديث خطة الوقاية.")
    return "\n".join(lines)


def _build_general_agri_answer(question, analytics):
    topics = _find_general_topics(question)
    lines = ["إجابة زراعية عملية على سؤالك:"]

    if topics:
        for topic in topics[:2]:
            lines.append("1) " + topic["advice"][0])
            lines.append("2) " + topic["advice"][1])
            lines.append("3) " + topic["advice"][2])
    else:
        lines.extend(
            [
                "1) ابدأ بتحديد المشكلة: هل هي نمو، مرض، آفة، ري، أم تغذية؟",
                "2) اعمل فحص ميداني سريع (10 نباتات من نقاط مختلفة).",
                "3) سجل الملاحظات باليوم والتاريخ لمقارنة التحسن خلال أسبوع.",
            ]
        )

    if analytics.get("top_diseases"):
        lines.append("معلومة من بياناتك: أكثر المشكلات تكرارا حاليا هي " + ", ".join(item["name"] for item in analytics["top_diseases"][:3]) + ".")

    lines.append("إذا أردت جواب أدق، اكتب: المحصول + العرض + عمر النبات + حالة الطقس.")
    lines.append("تنبيه مهني: هذا توجيه مساعد وليس بديلا عن الفحص الحقلي المباشر.")
    return "\n".join(lines)


def _build_local_expert_answer(user_question, analytics, history, image_context=None):
    effective_question = _expand_question_with_context(user_question, history)
    intent = _detect_intent(effective_question)
    has_inventory_match = bool(_match_inventory_medicines(effective_question, analytics))

    if intent == "general" and has_inventory_match:
        intent = "medicine_usage"

    if image_context:
        prefix = [
            "تم استلام الصورة، لكن المحرك المحلي لا ينفذ رؤية حاسوبية مباشرة.",
            "اكتب الأعراض الظاهرة (لون البقع، مكانها، سرعة الانتشار) وسأعطيك تشخيصًا أوليًا أدق.",
        ]
        return "\n".join(prefix + [_build_disease_answer(effective_question, analytics)])

    if intent == "weekly_report":
        return _build_weekly_report_answer(analytics)
    if intent == "medicine_compare":
        return _build_medicine_comparison_answer(effective_question, analytics)
    if intent == "weekly_plan":
        return _build_weekly_plan_answer(effective_question, analytics)
    if intent == "alerts":
        return _build_alerts_answer(analytics)
    if intent == "analysis":
        return _build_analysis_answer(analytics)
    if intent == "medicine_types":
        return _build_medicine_types_answer(effective_question, analytics)
    if intent == "medicine_usage":
        return _build_medicine_usage_answer(effective_question, analytics)
    if intent == "disease":
        return _build_disease_answer(effective_question, analytics)
    return _build_general_agri_answer(effective_question, analytics)


def _generate_answer(user_question, analytics, history, image_context=None):
    prompt = _build_prompt(user_question, analytics, history, image_context=image_context)
    config = _effective_remote_config()
    provider = config["provider"]

    ordered_backends = []
    if provider == "gemini":
        ordered_backends = ["gemini"]
    elif provider == "openai":
        ordered_backends = ["openai"]
    elif provider == "auto":
        ordered_backends = ["gemini", "openai"]
    elif provider == "local":
        ordered_backends = []

    last_error = None
    for backend in ordered_backends:
        if backend == "gemini":
            remote_answer, remote_error = _ask_gemini(
                prompt,
                api_key=config["gemini_key"],
                model=config["gemini_model"],
                image_context=image_context,
            )
            if remote_answer:
                return remote_answer, "gemini_api", None
            last_error = remote_error
            continue

        if backend == "openai":
            remote_answer, remote_error = _ask_openai(
                prompt,
                api_key=config["openai_key"],
                model=config["openai_model"],
                image_context=image_context,
            )
            if remote_answer:
                return remote_answer, "openai_api", None
            last_error = remote_error
            continue

    local_answer = _build_local_expert_answer(
        user_question,
        analytics,
        history,
        image_context=image_context,
    )
    return local_answer, "local_expert_engine", last_error or "local_only"


def _conversation_summaries(limit=50):
    rows = (
        db.session.query(
            AIConversation.id,
            AIConversation.title,
            AIConversation.created_at,
            AIConversation.updated_at,
            func.count(AIConversationMessage.id).label("message_count"),
        )
        .outerjoin(
            AIConversationMessage,
            AIConversationMessage.conversation_id == AIConversation.id,
        )
        .group_by(
            AIConversation.id,
            AIConversation.title,
            AIConversation.created_at,
            AIConversation.updated_at,
        )
        .order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .limit(limit)
        .all()
    )
    active_id = _active_conversation_id()
    return [
        {
            "id": row.id,
            "title": row.title or "محادثة جديدة",
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "message_count": int(row.message_count or 0),
            "is_active": bool(active_id and row.id == active_id),
        }
        for row in rows
    ]


@bp.route("/")
@login_required
def index():
    guard_response = _guard_access()
    if guard_response:
        return guard_response

    analytics = _collect_ai_analytics()
    chat_history = _read_history()
    chat_history_top = list(reversed(chat_history))
    ai_mode = _describe_ai_mode(_effective_remote_config())
    can_view_history = _can_view_ai_history()
    conversation_summaries = _conversation_summaries(limit=12) if can_view_history else []
    active_conversation = _get_active_conversation()

    return render_template(
        "ai/index.html",
        analytics=analytics,
        chat_history=chat_history,
        chat_history_top=chat_history_top,
        ai_mode=ai_mode,
        conversation_summaries=conversation_summaries,
        active_conversation=active_conversation,
        can_view_ai_history=can_view_history,
        can_use_ai_upload=_can_use_ai_upload(),
        can_use_ai_voice=_can_use_ai_voice(),
        can_view_ai_reports=_can_view_ai_reports(),
    )


@bp.route("/ask", methods=["POST"])
@login_required
def ask():
    guard_response = _guard_access()
    if guard_response:
        return guard_response

    user_question = (request.form.get("question") or "").strip()
    image_context, image_error, image_note = _extract_image_context_from_request()
    if image_error:
        flash(image_error, "warning")
        return redirect(url_for("ai_assistant.index"))

    if not user_question and not image_context:
        flash("اكتب سؤالا أولا", "warning")
        return redirect(url_for("ai_assistant.index"))

    if not user_question and image_context:
        user_question = "حلل الصورة المرفقة وقدم تشخيصا مبدئيا."

    analytics = _collect_ai_analytics()
    history = _read_history()
    answer, backend_used, fallback_reason = _generate_answer(
        user_question,
        analytics,
        history,
        image_context=image_context,
    )
    answer = _clean_assistant_output(answer)

    stored_question = user_question
    if image_note:
        stored_question = f"{user_question}\n[{image_note}]"

    history.append({"role": "user", "text": stored_question})
    history.append({"role": "assistant", "text": answer, "backend": backend_used})
    _save_history(history)

    try:
        conversation = _get_active_conversation()
        if not conversation:
            conversation = _create_conversation_from_question(user_question)
        _append_messages_to_conversation(conversation, stored_question, answer, backend_used)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("تعذر حفظ سجل المحادثة في قاعدة البيانات.", "warning")

    if fallback_reason == "no_api_key":
        flash("لم يتم العثور على مفتاح API للمزوّد المحدد. يمكنك إضافته من إعدادات الذكاء الاصطناعي.", "warning")
    elif fallback_reason and fallback_reason not in {"local_only"}:
        flash("تم استخدام المحرك المحلي لأن الاتصال بمزود الذكاء غير متاح حاليا.", "info")

    return redirect(url_for("ai_assistant.index"))


@bp.route("/clear", methods=["POST"])
@login_required
def clear():
    guard_response = _guard_access()
    if guard_response:
        return guard_response

    session.pop(_HISTORY_SESSION_KEY, None)
    _clear_active_conversation()
    session.modified = True
    flash("تم بدء محادثة جديدة", "success")
    return redirect(url_for("ai_assistant.index"))


@bp.route("/history")
@login_required
def history():
    guard_response = _guard_history_access()
    if guard_response:
        return guard_response

    conversations = _conversation_summaries(limit=150)
    return render_template("ai/history.html", conversations=conversations)


@bp.route("/history/<int:conversation_id>/open")
@login_required
def open_history(conversation_id):
    guard_response = _guard_history_access()
    if guard_response:
        return guard_response

    conversation = AIConversation.query.filter_by(id=conversation_id).first_or_404()
    history_rows = _load_history_from_conversation(conversation.id)
    if not history_rows:
        flash("هذه المحادثة لا تحتوي رسائل بعد.", "warning")
        return redirect(url_for("ai_assistant.history"))

    _set_active_conversation_id(conversation.id)
    _save_history(history_rows)
    flash("تم فتح سجل المحادثة.", "success")
    return redirect(url_for("ai_assistant.index"))


@bp.route("/weekly-report")
@login_required
def weekly_report():
    guard_response = _guard_reports_access()
    if guard_response:
        return guard_response

    analytics = _collect_ai_analytics()
    auto_summary = _build_weekly_report_answer(analytics)
    return render_template(
        "ai/weekly_report.html",
        analytics=analytics,
        auto_summary=auto_summary,
    )
