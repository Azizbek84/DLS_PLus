import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
import telebot
from telebot import types

load_dotenv()

# =================== KONFIGURATSIYA ===================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Majburiy obuna kanali
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@DLS_PLUS")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/DLS_PLUS")

# Admin yangi post qo'shganda, u avtomatik joylanadigan maxsus kanal.
# @username yoki raqamli ID (-100...) bo'lishi mumkin. Bo'sh bo'lsa - o'chirilgan.
_raw_post_channel = os.getenv("POST_CHANNEL_USERNAME", CHANNEL_USERNAME).strip()
if _raw_post_channel and _raw_post_channel.lstrip("-").isdigit():
    POST_CHANNEL_USERNAME = int(_raw_post_channel)
else:
    POST_CHANNEL_USERNAME = _raw_post_channel or None

ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "root")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "dls")

DB_FILE = Path(__file__).parent / "db.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dls_plus_bot")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env faylida BOT_TOKEN ni kiriting.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# =================== ODDIY JSON BAZA ===================
def load_db():
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    # Eski "news" formatidan yangi "kits" (klub -> postlar) formatiga o'tish
    if "kits" not in data:
        data["kits"] = {}
    data.setdefault("accounts", [])
    data.setdefault("admins", [])
    data.setdefault("users", [])
    return data


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


db = load_db()
save_db(db)


def track_user(user_id: int):
    if user_id not in db["users"]:
        db["users"].append(user_id)
        save_db(db)


def club_list():
    return sorted(db["kits"].keys())


def add_kit(club: str, text, photo):
    db["kits"].setdefault(club, [])
    db["kits"][club].append({"text": text, "photo": photo})
    save_db(db)


def get_latest_kit(club: str):
    posts = db["kits"].get(club, [])
    return posts[-1] if posts else None


def add_account(photo, price, level, description):
    db["accounts"].append(
        {"photo": photo, "price": price, "level": level, "description": description}
    )
    save_db(db)


def get_latest_account():
    return db["accounts"][-1] if db["accounts"] else None


def delete_kit(club: str, index: int) -> bool:
    posts = db["kits"].get(club, [])
    if 0 <= index < len(posts):
        posts.pop(index)
        save_db(db)
        return True
    return False


def delete_account(index: int) -> bool:
    accounts = db.get("accounts", [])
    if 0 <= index < len(accounts):
        accounts.pop(index)
        save_db(db)
        return True
    return False


def is_admin(user_id: int) -> bool:
    return user_id in db.get("admins", [])


def add_admin(user_id: int):
    if user_id not in db["admins"]:
        db["admins"].append(user_id)
        save_db(db)


# =================== HOLATLAR (oddiy state-machine) ===================
# user_id -> {"state": "...", "data": {...}}
user_states = {}


def set_state(user_id, state, data=None):
    user_states[user_id] = {"state": state, "data": data or {}}


def get_state(user_id):
    return user_states.get(user_id, {"state": None, "data": {}})


def clear_state(user_id):
    user_states.pop(user_id, None)


def in_state(state_name):
    return lambda m: get_state(m.from_user.id)["state"] == state_name


# =================== TUGMA MATNLARI ===================
BTN_CHECK_SUB = "✅ Obunani tekshirish"
BTN_NEWS = "🧩 DLS KIT"
BTN_ACCOUNTS = "🎮 DLS akkauntlar"
BTN_BACK_TO_MAIN = "⬅️ Orqaga"

BTN_ADMIN_ADD_NEWS = "🧩 DLS KIT qo'shish"
BTN_ADMIN_DELETE_KIT = "🗑️ DLS KIT o'chirish"
BTN_ADMIN_ADD_ACCOUNT = "🎮 Akkaunt qo'shish"
BTN_ADMIN_DELETE_ACCOUNT = "🗑️ Akkaunt o'chirish"
BTN_ADMIN_STATS = "📊 Statistika"
BTN_ADMIN_EXIT = "⬅️ Admin paneldan chiqish"

BTN_NEW_CLUB = "➕ Yangi klub qo'shish"
BTN_CANCEL = "❌ Bekor qilish"
BTN_SKIP = "➖ O'tkazib yuborish"


# =================== KLAVIATURALAR (Reply/Markup) ===================
def subscribe_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_CHECK_SUB))
    return kb


def main_menu_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_NEWS))
    kb.add(types.KeyboardButton(BTN_ACCOUNTS))
    return kb


def admin_menu_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_ADMIN_ADD_NEWS))
    kb.add(types.KeyboardButton(BTN_ADMIN_DELETE_KIT))
    kb.add(types.KeyboardButton(BTN_ADMIN_ADD_ACCOUNT))
    kb.add(types.KeyboardButton(BTN_ADMIN_DELETE_ACCOUNT))
    kb.add(types.KeyboardButton(BTN_ADMIN_STATS))
    kb.add(types.KeyboardButton(BTN_ADMIN_EXIT))
    return kb


def cancel_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_CANCEL))
    return kb


def skip_or_cancel_markup():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_SKIP))
    kb.add(types.KeyboardButton(BTN_CANCEL))
    return kb


def clubs_markup(clubs, include_new_club_button=False, back_button_text=BTN_CANCEL):
    """Klublar ro'yxatini rasmdagidek 2 tadan qatorga joylab chiqaradi."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if clubs:
        kb.add(*[types.KeyboardButton(c) for c in clubs])
    if include_new_club_button:
        kb.add(types.KeyboardButton(BTN_NEW_CLUB))
    kb.add(types.KeyboardButton(back_button_text))
    return kb


# =================== OBUNANI TEKSHIRISH ===================
def check_subscription(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.warning(f"Obunani tekshirishda xato: {e}")
        return False


def require_subscription(chat_id, user_id) -> bool:
    if check_subscription(user_id):
        return True
    bot.send_message(
        chat_id,
        "Botdan foydalanish uchun avval quyidagi kanalga obuna bo'ling ❌\n\n"
        f"{CHANNEL_URL}\n\n"
        f"Obuna bo'lgach, \"{BTN_CHECK_SUB}\" tugmasini bosing.",
        reply_markup=subscribe_markup(),
    )
    return False


# =================== /start ===================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    track_user(message.from_user.id)
    if not require_subscription(message.chat.id, message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "Xush kelibsiz! Kerakli bo'limni tanlang 👇",
        reply_markup=main_menu_markup(),
    )


@bot.message_handler(func=lambda m: m.text == BTN_CHECK_SUB)
def check_sub_handler(message):
    if check_subscription(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Rahmat! Endi kerakli bo'limni tanlang 👇",
            reply_markup=main_menu_markup(),
        )
    else:
        bot.send_message(
            message.chat.id,
            f"Siz hali kanalga obuna bo'lmadingiz ❌\n{CHANNEL_URL}",
            reply_markup=subscribe_markup(),
        )


# =================== ADMIN LOGIN ===================
@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Admin panel:", reply_markup=admin_menu_markup())
        return
    set_state(message.from_user.id, "admin_login")
    bot.send_message(message.chat.id, "🔐 Login kiriting:", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=in_state("admin_login"))
def admin_login_handler(message):
    if message.text == ADMIN_LOGIN:
        set_state(message.from_user.id, "admin_password")
        bot.send_message(message.chat.id, "🔑 Parol kiriting:")
    else:
        clear_state(message.from_user.id)
        bot.send_message(
            message.chat.id,
            "Login noto'g'ri. Qaytadan urinish uchun /admin buyrug'ini yuboring.",
            reply_markup=main_menu_markup(),
        )


@bot.message_handler(func=in_state("admin_password"))
def admin_password_handler(message):
    if message.text == ADMIN_PASSWORD:
        add_admin(message.from_user.id)
        clear_state(message.from_user.id)
        bot.send_message(
            message.chat.id,
            "✅ Tizimga muvaffaqiyatli kirdingiz!",
            reply_markup=admin_menu_markup(),
        )
    else:
        clear_state(message.from_user.id)
        bot.send_message(
            message.chat.id,
            "Parol noto'g'ri. Qaytadan urinish uchun /admin buyrug'ini yuboring.",
            reply_markup=main_menu_markup(),
        )


# =================== KANALGA AVTOMATIK POST ===================
def post_kit_to_channel(club, text, photo) -> bool:
    if not POST_CHANNEL_USERNAME:
        return False
    header = f"👕 <b>Yangi DLS KIT — {club}!</b>"
    full_text = f"{header}\n\n{text}" if text else header
    try:
        if photo:
            bot.send_photo(POST_CHANNEL_USERNAME, photo, caption=full_text)
        else:
            bot.send_message(POST_CHANNEL_USERNAME, full_text)
        return True
    except Exception as e:
        logger.warning(f"Kanalga DLS KIT post qilishda xato: {e}")
        return False


def post_account_to_channel(photo, caption) -> bool:
    if not POST_CHANNEL_USERNAME:
        return False
    try:
        bot.send_photo(POST_CHANNEL_USERNAME, photo, caption=caption)
        return True
    except Exception as e:
        logger.warning(f"Kanalga akkaunt post qilishda xato: {e}")
        return False


def channel_result_line(ok: bool) -> str:
    if ok:
        return f"\n📢 Kanalga ({POST_CHANNEL_USERNAME}) ham joylandi."
    if POST_CHANNEL_USERNAME:
        return "\n⚠️ Kanalga joylashda xatolik (botni kanalga admin qilib qo'shganingizni tekshiring)."
    return ""


def format_account_caption(post) -> str:
    lines = ["🎮 <b>DLS Akkaunt sotuvda!</b>", ""]
    if post.get("level"):
        lines.append(f"⭐ <b>Level:</b> {post['level']}")
    if post.get("price"):
        lines.append(f"💰 <b>Narxi:</b> {post['price']}")
    if post.get("description"):
        lines.append("")
        lines.append(post["description"])
    return "\n".join(lines)


# =================== ADMIN: DLS KIT QO'SHISH (klub tanlash / yangi klub) ===================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_ADD_NEWS)
def admin_add_kit_start(message):
    set_state(message.from_user.id, "admin_kit_menu")
    bot.send_message(
        message.chat.id,
        "Qaysi klubga kit qo'shmoqchisiz? Ro'yxatdan tanlang, "
        "yoki yangi klub yarating 👇",
        reply_markup=clubs_markup(club_list(), include_new_club_button=True),
    )


@bot.message_handler(func=in_state("admin_kit_menu"))
def admin_kit_menu_handler(message):
    uid = message.from_user.id
    text = message.text

    if text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    if text == BTN_NEW_CLUB:
        set_state(uid, "admin_kit_new_name")
        bot.send_message(
            message.chat.id,
            "Yangi klub nomini kiriting (masalan: Real Madrid):",
            reply_markup=cancel_markup(),
        )
        return

    if text in db["kits"]:
        set_state(uid, "admin_kit_content", {"club": text})
        bot.send_message(
            message.chat.id,
            f"\"{text}\" uchun yangi kit yuboring:\n\n"
            "• Matn yuborishingiz mumkin\n"
            "• Yoki rasm + izoh (caption) shaklida yuborishingiz mumkin",
            reply_markup=cancel_markup(),
        )
        return

    # Admin boshqa admin-menyu tugmasini bosgan bo'lishi mumkin - shunga yo'naltiramiz
    if text == BTN_ADMIN_ADD_ACCOUNT:
        clear_state(uid)
        admin_add_account_start(message)
        return
    if text == BTN_ADMIN_DELETE_KIT:
        clear_state(uid)
        admin_delete_kit_start(message)
        return
    if text == BTN_ADMIN_DELETE_ACCOUNT:
        clear_state(uid)
        admin_delete_account_start(message)
        return
    if text == BTN_ADMIN_STATS:
        clear_state(uid)
        admin_stats(message)
        return
    if text == BTN_ADMIN_EXIT:
        clear_state(uid)
        admin_exit(message)
        return

    bot.send_message(
        message.chat.id,
        "Iltimos, ro'yxatdagi klubni tanlang yoki \"➕ Yangi klub qo'shish\" tugmasini bosing.",
        reply_markup=clubs_markup(club_list(), include_new_club_button=True),
    )


@bot.message_handler(func=in_state("admin_kit_new_name"))
def admin_kit_new_name_handler(message):
    uid = message.from_user.id
    if message.text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    club_name = (message.text or "").strip()
    if not club_name:
        bot.send_message(message.chat.id, "Klub nomi bo'sh bo'lmasin. Qaytadan kiriting:")
        return
    if club_name in db["kits"]:
        bot.send_message(
            message.chat.id,
            f"\"{club_name}\" klubi allaqachon mavjud. Ro'yxatdan tanlang yoki boshqa nom kiriting.",
        )
        return

    set_state(uid, "admin_kit_content", {"club": club_name})
    bot.send_message(
        message.chat.id,
        f"\"{club_name}\" uchun birinchi kitni yuboring:\n\n"
        "• Matn yuborishingiz mumkin\n"
        "• Yoki rasm + izoh (caption) shaklida yuborishingiz mumkin",
        reply_markup=cancel_markup(),
    )


@bot.message_handler(content_types=["text", "photo"], func=in_state("admin_kit_content"))
def admin_kit_content_handler(message):
    uid = message.from_user.id
    if message.content_type == "text" and message.text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    data = get_state(uid)["data"]
    club = data["club"]
    text = message.text or message.caption
    photo = message.photo[-1].file_id if message.photo else None

    if not text and not photo:
        bot.send_message(message.chat.id, "Iltimos matn yoki rasm yuboring.")
        return

    add_kit(club, text, photo)
    clear_state(uid)
    ok = post_kit_to_channel(club, text, photo)
    bot.send_message(
        message.chat.id,
        f"✅ \"{club}\" uchun yangi kit qo'shildi!" + channel_result_line(ok),
        reply_markup=admin_menu_markup(),
    )


# =================== ADMIN: AKKAUNT QO'SHISH (rasm -> narx -> level -> tavsif) ===================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_ADD_ACCOUNT)
def admin_add_account_start(message):
    set_state(message.from_user.id, "acc_wait_photo", {})
    bot.send_message(message.chat.id, "1/4. Akkaunt rasmini yuboring:", reply_markup=cancel_markup())


@bot.message_handler(content_types=["text", "photo"], func=in_state("acc_wait_photo"))
def admin_add_account_photo(message):
    if message.content_type == "text" and message.text == BTN_CANCEL:
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return
    if not message.photo:
        bot.send_message(message.chat.id, "Iltimos, rasm yuboring (yoki bekor qilish uchun tugmani bosing).")
        return
    photo = message.photo[-1].file_id
    set_state(message.from_user.id, "acc_wait_price", {"photo": photo})
    bot.send_message(message.chat.id, "2/4. Akkaunt narxini kiriting (masalan: 150 000 so'm):", reply_markup=cancel_markup())


@bot.message_handler(func=in_state("acc_wait_price"))
def admin_add_account_price(message):
    if message.text == BTN_CANCEL:
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return
    data = get_state(message.from_user.id)["data"]
    data["price"] = message.text
    set_state(message.from_user.id, "acc_wait_level", data)
    bot.send_message(message.chat.id, "3/4. Akkaunt levelini kiriting (masalan: Level 130):", reply_markup=cancel_markup())


@bot.message_handler(func=in_state("acc_wait_level"))
def admin_add_account_level(message):
    if message.text == BTN_CANCEL:
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return
    data = get_state(message.from_user.id)["data"]
    data["level"] = message.text
    set_state(message.from_user.id, "acc_wait_desc", data)
    bot.send_message(
        message.chat.id,
        "4/4. Qo'shimcha ma'lumot kiriting (masalan: qanday itemlar/skinlar bor).\n"
        f"Kerak bo'lmasa \"{BTN_SKIP}\" tugmasini bosing:",
        reply_markup=skip_or_cancel_markup(),
    )


@bot.message_handler(func=in_state("acc_wait_desc"))
def admin_add_account_desc(message):
    if message.text == BTN_CANCEL:
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    data = get_state(message.from_user.id)["data"]
    description = "" if message.text == BTN_SKIP else message.text

    add_account(data["photo"], data["price"], data["level"], description)
    clear_state(message.from_user.id)

    post = {"photo": data["photo"], "price": data["price"], "level": data["level"], "description": description}
    caption = format_account_caption(post)
    ok = post_account_to_channel(post["photo"], caption)

    bot.send_message(
        message.chat.id,
        "✅ Yangi akkaunt qo'shildi!" + channel_result_line(ok),
        reply_markup=admin_menu_markup(),
    )


# =================== ADMIN: DLS KIT O'CHIRISH ===================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_DELETE_KIT)
def admin_delete_kit_start(message):
    clubs = club_list()
    if not clubs:
        bot.send_message(message.chat.id, "Hozircha klub yo'q.", reply_markup=admin_menu_markup())
        return
    set_state(message.from_user.id, "del_kit_club")
    bot.send_message(
        message.chat.id,
        "Qaysi klubning kitini o'chirmoqchisiz? Ro'yxatdan tanlang 👇",
        reply_markup=clubs_markup(clubs),
    )


@bot.message_handler(func=in_state("del_kit_club"))
def admin_delete_kit_club_handler(message):
    uid = message.from_user.id
    text = message.text
    if text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    if text not in db["kits"]:
        bot.send_message(message.chat.id, "Iltimos, ro'yxatdagi klubni tanlang.")
        return

    posts = db["kits"][text]
    if not posts:
        bot.send_message(message.chat.id, f"\"{text}\" klubida kit yo'q.", reply_markup=admin_menu_markup())
        clear_state(uid)
        return

    lines = [f"🏳️ <b>{text}</b> klubi kitlari (oxirgisidan boshlab):", ""]
    for i, post in enumerate(reversed(posts)):
        idx = len(posts) - 1 - i
        snippet = (post.get("text") or "(rasm)")[:40].replace("\n", " ")
        lines.append(f"{i + 1}) [{idx}] {snippet}")
    lines.append("")
    lines.append("O'chirmoqchi bo'lgan kitingizning <b>raqamini</b> kiriting (1 dan boshlab):")

    set_state(uid, "del_kit_index", {"club": text, "total": len(posts)})
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=cancel_markup())


@bot.message_handler(func=in_state("del_kit_index"))
def admin_delete_kit_index_handler(message):
    uid = message.from_user.id
    if message.text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    state = get_state(uid)
    club = state["data"]["club"]
    total = state["data"]["total"]

    try:
        num = int(message.text)
    except (ValueError, TypeError):
        bot.send_message(message.chat.id, "Iltimos, raqam kiriting.")
        return

    if num < 1 or num > total:
        bot.send_message(message.chat.id, f"Raqam 1 dan {total} gacha bo'lishi kerak.")
        return

    real_index = total - num
    if delete_kit(club, real_index):
        clear_state(uid)
        bot.send_message(
            message.chat.id,
            f"✅ \"{club}\" klubidan {num}-kit o'chirildi.",
            reply_markup=admin_menu_markup(),
        )
    else:
        bot.send_message(message.chat.id, "O'chirishda xato yuz berdi.")


# =================== ADMIN: AKKAUNT O'CHIRISH ===================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_DELETE_ACCOUNT)
def admin_delete_account_start(message):
    accounts = db.get("accounts", [])
    if not accounts:
        bot.send_message(message.chat.id, "Hozircha akkaunt yo'q.", reply_markup=admin_menu_markup())
        return

    lines = ["🎮 <b>Sotuvdagi akkauntlar</b> (oxirgisidan boshlab):", ""]
    for i, acc in enumerate(reversed(accounts)):
        idx = len(accounts) - 1 - i
        info = []
        if acc.get("level"):
            info.append(acc["level"])
        if acc.get("price"):
            info.append(acc["price"])
        desc = (acc.get("description") or "").replace("\n", " ")[:30]
        if desc:
            info.append(desc)
        lines.append(f"{i + 1}) [{idx}] " + " | ".join(info) if info else f"{i + 1}) [{idx}] (ma'lumot yo'q)")
    lines.append("")
    lines.append("O'chirmoqchi bo'lgan akkauntingizning <b>raqamini</b> kiriting (1 dan boshlab):")

    set_state(message.from_user.id, "del_acc_index", {"total": len(accounts)})
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=cancel_markup())


@bot.message_handler(func=in_state("del_acc_index"))
def admin_delete_account_index_handler(message):
    uid = message.from_user.id
    if message.text == BTN_CANCEL:
        clear_state(uid)
        bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=admin_menu_markup())
        return

    total = get_state(uid)["data"]["total"]
    try:
        num = int(message.text)
    except (ValueError, TypeError):
        bot.send_message(message.chat.id, "Iltimos, raqam kiriting.")
        return

    if num < 1 or num > total:
        bot.send_message(message.chat.id, f"Raqam 1 dan {total} gacha bo'lishi kerak.")
        return

    real_index = total - num
    if delete_account(real_index):
        clear_state(uid)
        bot.send_message(
            message.chat.id,
            f"✅ {num}-akkaunt o'chirildi.",
            reply_markup=admin_menu_markup(),
        )
    else:
        bot.send_message(message.chat.id, "O'chirishda xato yuz berdi.")


# =================== ADMIN: STATISTIKA / CHIQISH ===================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_STATS)
def admin_stats(message):
    total_kits = sum(len(posts) for posts in db["kits"].values())
    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Botdan foydalanganlar: <b>{len(db.get('users', []))}</b>\n"
        f"🏳️ Klublar soni: <b>{len(db['kits'])}</b>\n"
        f"🧩 Jami DLS KIT postlari: <b>{total_kits}</b>\n"
        f"🎮 Sotuvga qo'yilgan akkauntlar: <b>{len(db.get('accounts', []))}</b>\n"
        f"👤 Adminlar soni: <b>{len(db.get('admins', []))}</b>"
    )
    bot.send_message(message.chat.id, text, reply_markup=admin_menu_markup())


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_ADMIN_EXIT)
def admin_exit(message):
    clear_state(message.from_user.id)
    bot.send_message(message.chat.id, "Admin paneldan chiqdingiz.", reply_markup=main_menu_markup())


@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == BTN_CANCEL)
def admin_stray_cancel(message):
    bot.send_message(message.chat.id, "Admin panel:", reply_markup=admin_menu_markup())


# =================== FOYDALANUVCHI: DLS KIT (klublar bo'yicha) ===================
@bot.message_handler(func=lambda m: m.text == BTN_NEWS)
def news_handler(message):
    if not require_subscription(message.chat.id, message.from_user.id):
        return
    clubs = club_list()
    if not clubs:
        bot.send_message(message.chat.id, "Hozircha DLS KIT bo'yicha hech narsa yo'q.", reply_markup=main_menu_markup())
        return
    bot.send_message(
        message.chat.id,
        "Klubni tanlang 👇",
        reply_markup=clubs_markup(clubs, back_button_text=BTN_BACK_TO_MAIN),
    )


@bot.message_handler(func=lambda m: m.text in db["kits"])
def club_kit_handler(message):
    if not require_subscription(message.chat.id, message.from_user.id):
        return
    club = message.text
    post = get_latest_kit(club)
    kb = clubs_markup(club_list(), back_button_text=BTN_BACK_TO_MAIN)
    if not post:
        bot.send_message(message.chat.id, f"\"{club}\" uchun hozircha kit yo'q.", reply_markup=kb)
        return
    caption = f"👕 <b>{club} — DLS KIT</b>\n\n{post.get('text') or ''}".strip()
    if post.get("photo"):
        bot.send_photo(message.chat.id, post["photo"], caption=caption, reply_markup=kb)
    else:
        bot.send_message(message.chat.id, caption, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == BTN_BACK_TO_MAIN)
def back_to_main_handler(message):
    bot.send_message(message.chat.id, "Kerakli bo'limni tanlang 👇", reply_markup=main_menu_markup())


# =================== FOYDALANUVCHI: AKKAUNTLAR ===================
@bot.message_handler(func=lambda m: m.text == BTN_ACCOUNTS)
def accounts_handler(message):
    if not require_subscription(message.chat.id, message.from_user.id):
        return
    post = get_latest_account()
    if not post:
        bot.send_message(message.chat.id, "Hozircha sotuvda akkaunt yo'q.", reply_markup=main_menu_markup())
        return
    caption = format_account_caption(post)
    if post.get("photo"):
        bot.send_photo(message.chat.id, post["photo"], caption=caption, reply_markup=main_menu_markup())
    else:
        bot.send_message(message.chat.id, caption, reply_markup=main_menu_markup())


# =================== ISHGA TUSHIRISH ===================
if __name__ == "__main__":
    logger.info("DLS PLUS bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
