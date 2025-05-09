# main.py
import os, json, multiprocessing, logging
from telegram import (
    Update, Bot,
    ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)

# ────── Константы ──────
CONSTRUCTOR_TOKEN = "7952794259:AAHCLUk7Zw-DOqfJSFWrda4rOjWp3B_CqQY"
ADMIN_USERNAME    = "SAKI_n_tosh"
BOTS_FILE         = "bots.json"

# ────── Глобальные хранилища ──────
processes   = {}             # token -> multiprocessing.Process
WAIT_FOR    = {}             # chat_id -> state
BCAST_DATA  = {}             # chat_id -> {"text": str, "button": (label,url)|None}

# ────── Утилиты ──────
def load_tokens():
    if not os.path.exists(BOTS_FILE):
        json.dump([], open(BOTS_FILE, "w"))
    return json.load(open(BOTS_FILE))

def save_tokens(tokens):
    json.dump(tokens, open(BOTS_FILE, "w"), indent=2)

def spawn_bot(token):
    from anon_chat_bot import main as anon_main
    p = multiprocessing.Process(target=anon_main, args=(token,))
    p.daemon = True
    p.start()
    processes[token] = p

def only_admin(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.username != ADMIN_USERNAME:
            return await update.message.reply_text("🚫 Доступ только администратору.")
        return await func(update, ctx)
    return wrapper

# ────── Команды ──────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [
            ["/addbot", "/bots"],
            ["/analytics", "/broadcast"],
            ["/setdesc", "/setad"],
        ],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "👋 Привет! Это Конструктор анонимных чатов.\n\n"
        "Выбери команду на клавиатуре.",
        reply_markup=kb
    )

@only_admin
async def cmd_addbot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    WAIT_FOR[update.effective_chat.id] = "token"
    await update.message.reply_text("📥 Отправь токен нового бота:")

@only_admin
async def cmd_bots(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = []
    for t in load_tokens():
        alive = "🟢" if processes.get(t) and processes[t].is_alive() else "🔴"
        lines.append(f"{t[:10]}… — {alive}")
    await update.message.reply_text("🤖 Список ботов:\n" + "\n".join(lines))

@only_admin
async def cmd_analytics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total, lines = 0, []
    for t in load_tokens():
        path = os.path.join("data", "subs.json")
        try:
            cnt = len(json.load(open(path)))
        except: cnt = 0
        total += cnt
        lines.append(f"{t[:10]}… — {cnt}")
    await update.message.reply_text(
        "📊 Подписчики:\n" + "\n".join(lines) + f"\n\nВсего: {total}"
    )

@only_admin
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    WAIT_FOR[update.effective_chat.id] = "bcast_text"
    await update.message.reply_text("📝 Отправь текст рассылки:")

@only_admin
async def cmd_setdesc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    WAIT_FOR[update.effective_chat.id] = "desc"
    await update.message.reply_text("📄 Отправь новый description:")

@only_admin
async def cmd_setad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    WAIT_FOR[update.effective_chat.id] = "ad"
    await update.message.reply_text("📢 Отправь новый short_description:")

# ────── Универсальный текстовый хэндлер ──────
@only_admin
async def text_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid   = update.effective_chat.id
    state = WAIT_FOR.get(cid)
    text  = update.message.text.strip()

    # -------- ADD BOT --------
    if state == "token":
        token = text
        try:
            await Bot(token).get_me()
        except:
            return await update.message.reply_text("❗ Неверный токен.")
        tokens = load_tokens()
        if token in tokens:
            return await update.message.reply_text("❗ Этот бот уже добавлен.")
        tokens.append(token); save_tokens(tokens); spawn_bot(token)
        await update.message.reply_text("✅ Бот добавлен и запущен.")
        WAIT_FOR.pop(cid, None)

    # -------- BCAST: текст --------
    elif state == "bcast_text":
        BCAST_DATA[cid] = {"text": text, "button": None}
        WAIT_FOR[cid]   = "bcast_button"
        await update.message.reply_text(
            "🔘 Отправь `label|URL` или `label URL` для кнопки.\n"
            "Напиши `nobutton`, чтобы без кнопки.",
            parse_mode="Markdown"
        )

    # -------- BCAST: кнопка / nobutton --------
    elif state == "bcast_button":
        data = BCAST_DATA[cid]
        if text.lower().lstrip("/") == "nobutton":
            button = None
        else:
            if "|" in text: parts = text.split("|", 1)
            elif " " in text: parts = text.split(" ", 1)
            else:
                return await update.message.reply_text(
                    "❗ Формат неверен. Нужно `label|URL`, `label URL` или `nobutton`."
                )
            button = (parts[0].strip(), parts[1].strip())
        data["button"] = button

        # Рассылка
        sent = 0
        for tok in load_tokens():
            try:
                subs = json.load(open(os.path.join("data", "subs.json")))
            except: subs = {}
            bot = Bot(tok)
            for uid in subs.keys():
                try:
                    if button:
                        kb = InlineKeyboardMarkup(
                            [[InlineKeyboardButton(button[0], url=button[1])]]
                        )
                        await bot.send_message(int(uid), data["text"], reply_markup=kb)
                    else:
                        await bot.send_message(int(uid), data["text"])
                    sent += 1
                except: pass
        await update.message.reply_text(f"✅ Отправлено: {sent}")
        WAIT_FOR.pop(cid, None)
        BCAST_DATA.pop(cid, None)

    # -------- setdesc --------
    elif state == "desc":
        ok = 0
        for tok in load_tokens():
            try:
                await Bot(tok).set_my_description(description=text); ok += 1
            except: pass
        await update.message.reply_text(f"✅ Обновлено описаний: {ok}")
        WAIT_FOR.pop(cid, None)

    # -------- setad --------
    elif state == "ad":
        ok = 0
        for tok in load_tokens():
            try:
                await Bot(tok).set_my_short_description(short_description=text); ok += 1
            except: pass
        await update.message.reply_text(f"✅ Обновлено short_description: {ok}")
        WAIT_FOR.pop(cid, None)

    # -------- Ничего не ждём --------
    else:
        await update.message.reply_text("❗ Команда не ожидается. Используй меню /start.")

# ────── Запуск приложения ──────
def main():
    logging.basicConfig(level=logging.INFO)

    # Автозапуск ранее добавленных ботов
    for tok in load_tokens():
        spawn_bot(tok)

    app = Application.builder().token(CONSTRUCTOR_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("addbot",    cmd_addbot))
    app.add_handler(CommandHandler("bots",      cmd_bots))
    app.add_handler(CommandHandler("analytics", cmd_analytics))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("setdesc",   cmd_setdesc))
    app.add_handler(CommandHandler("setad",     cmd_setad))

    # принимаем абсолютно любой текст (включая /nobutton)
    app.add_handler(MessageHandler(filters.TEXT, text_router))

    app.run_polling()

if __name__ == "__main__":
    main()
