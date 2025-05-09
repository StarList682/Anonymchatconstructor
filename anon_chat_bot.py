# anon_chat_bot.py

import os
import json
import time
import logging
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# — Папка для данных —
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

WAIT_F   = os.path.join(DATA_DIR, "wait.json")
CHATS_F  = os.path.join(DATA_DIR, "chats.json")
COMPL_F  = os.path.join(DATA_DIR, "complaints.json")
BANS_F   = os.path.join(DATA_DIR, "bans.json")
SUBS_F   = os.path.join(DATA_DIR, "subs.json")

ADMIN_CONTACT = "https://t.me/SAKI_n_tosh"

# Инициализация файлов
for path in (WAIT_F, CHATS_F, COMPL_F, BANS_F, SUBS_F):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

def load(path):
    with open(path, "r") as f:
        return json.load(f)

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def is_banned(user_id):
    bans = load(BANS_F)
    ts = bans.get(str(user_id))
    if ts and time.time() < ts:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    return False

def add_sub(user_id):
    subs = load(SUBS_F)
    subs[str(user_id)] = True
    save(SUBS_F, subs)

# — /start —
async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_banned(uid):
        return await update.message.reply_text(f"🚫 Вы забанены до {is_banned(uid)}")

    add_sub(uid)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 Начать чат", callback_data="START_CHAT"),
        InlineKeyboardButton("📞 Контакт админа", url=ADMIN_CONTACT),
    ]])
    text = (
        "👤 *Анонимный чат*\n\n"
        "– Жмите «Начать чат», чтобы найти собеседника.\n"
        "– /stop или «Выйти» — закончить текущий чат.\n"
        "– /ban — пожаловаться на текущего собеседника.\n\n"
        "При 10 жалобах одному пользователю, он будет заблокирован на 3 дня."
    )
    await update.message.reply_markdown(text, reply_markup=kb)

# — Поиск собеседника —
async def start_chat_cb(update, ctx):
    query = update.callback_query
    uid   = query.from_user.id
    await query.answer()

    if is_banned(uid):
        return await query.edit_message_text(f"🚫 Вы забанены до {is_banned(uid)}")

    wait  = load(WAIT_F)
    chats = load(CHATS_F)

    # Если уже в чате
    if str(uid) in chats:
        return await query.edit_message_text("❗ Вы уже в чате. /stop — выйти.")

    # Если кто-то ждёт
    if wait:
        other_id, _ = wait.popitem()
        # Не соединяем с самим собой
        if other_id == uid:
            # оставляем его в очереди, ждём дальше
            wait[str(uid)] = time.time()
            save(WAIT_F, wait)
            return await query.edit_message_text("⏳ Ожидание другого партнёра...")
        # Создаём чат
        chats[str(uid)]      = other_id
        chats[str(other_id)] = uid
        save(WAIT_F, wait)
        save(CHATS_F, chats)
        await ctx.bot.send_message(other_id, "✅ Найден собеседник! Пишите. /stop — завершить, /ban - жалоба.")
        await ctx.bot.send_message(uid,       "✅ Найден собеседник! Пишите. /stop — завершить, /ban - жалоба.")
    else:
        # Ставим в очередь
        wait[str(uid)] = time.time()
        save(WAIT_F, wait)
        await query.edit_message_text("⏳ Ожидайте подключения собеседника...")

# — Выход из чата (кнопка или /stop) —
async def stop_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    chats = load(CHATS_F)
    partner = chats.pop(str(uid), None)
    if partner:
        chats.pop(str(partner), None)
        save(CHATS_F, chats)
        await ctx.bot.send_message(partner, "🔴 Ваш собеседник вышел из чата.")
        return await update.message.reply_text("🔴 Вы вышли из чата.")
    return await update.message.reply_text("❗ Вы сейчас не в чате.")

# — Жалоба /ban (1 раз на партнёра) —
async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    chats = load(CHATS_F)
    partner = chats.get(str(uid))
    if not partner:
        return await update.message.reply_text("❗ Вы не в чате, жаловаться не на кого.")

    comp = load(COMPL_F)
    key = f"{uid}:{partner}"
    # проверяем, не жаловался ли уже
    if comp.get(key):
        return await update.message.reply_text("❗ Вы уже отправили жалобу этому собеседнику.")

    # делаем жалобу
    comp[key] = True
    cnt, stamps = load(COMPL_F).get(str(partner), (0, []))
    cnt += 1; stamps.append(time.time())
    all_comp = load(COMPL_F)
    all_comp[str(partner)] = (cnt, stamps)
    all_comp[key] = True  # маркер, что именно вы жаловались
    save(COMPL_F, all_comp)

    msg = f"📣 Жалоба принята. У пользователя теперь {cnt} жалоб."
    await update.message.reply_text(msg)

    # баним партнёра при 10 жалобах
    if cnt >= 10:
        bans = load(BANS_F)
        bans[str(partner)] = time.time() + 3 * 24 * 3600
        save(BANS_F, bans)

        # разрываем чат
        chats.pop(str(partner), None)
        chats.pop(str(uid), None)
        save(CHATS_F, chats)

        await ctx.bot.send_message(partner, "🚫 Вас заблокировали на 3 дня за жалобы.")

# — Реле сообщений —
async def relay_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_banned(uid):
        return await update.message.reply_text(f"🚫 Вы забанены до {is_banned(uid)}")

    chats = load(CHATS_F)
    partner = chats.get(str(uid))
    if not partner:
        return await update.message.reply_text("❗ Вы не в чате. Нажмите «Начать чат» или /start.")
    if update.message.text:
        await ctx.bot.send_message(partner, update.message.text)

def main(token: str):
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(start_chat_cb, pattern="^START_CHAT$"))
    app.add_handler(CallbackQueryHandler(stop_chat,     pattern="^STOP_CHAT$"))
    app.add_handler(CommandHandler("stop",  stop_chat))
    app.add_handler(CommandHandler("ban",   ban_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_msg))

    app.run_polling()

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Использование: python anon_chat_bot.py <TOKEN>")
        sys.exit(1)
    main(sys.argv[1])
