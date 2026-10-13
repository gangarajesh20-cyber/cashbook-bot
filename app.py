import os
import logging
import sqlite3
import pandas as pd
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8905066918:AAGqIHCrvt4t_Z_BOXB16SO7Aus3XO0YKC8"
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

USER_NAMES = {
    6394258624: "RAJA ( THE GOD )",
    8941572137: "DUMBU (THE DEVIL)"
}
ALLOWED_USERS = list(USER_NAMES.keys())
# =======================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('cashbook.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            type TEXT,
            amount REAL,
            category TEXT,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

app = Flask(__name__)
telegram_app = None

main_keyboard = [
    ['➕ Add Expense', '💵 Add Income'],
    ['📊 Cash Book Summary', '🤝 Settlement Status'],
    ['📥 Export Cash Book', '❓ Help']
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, selective=True)

def is_authorized(user_id):
    return user_id in ALLOWED_USERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("🚫 Unauthorized access.")
        return
    display_name = USER_NAMES.get(user_id, "User")
    welcome_text = (
        f"👑 Welcome **{display_name}**!\n\n"
        "This bot tracks combined Income, Expenses, and Cash Book data for both of you.\n\n"
        "**Quick Command Usage:**\n"
        "• `/exp <amount> <category> <description>`\n"
        "• `/inc <amount> <category> <description>`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=markup)

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ Usage: `/exp <amount> <category> [description]`", parse_mode="Markdown")
            return
        amount = float(args[0])
        category = args[1]
        description = " ".join(args[2:]) if len(args) > 2 else "N/A"
        display_name = USER_NAMES.get(user.id, user.first_name)

        conn = sqlite3.connect('cashbook.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (user_id, username, type, amount, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                       (user.id, display_name, 'EXPENSE', amount, category, description))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ **Expense Logged!**\n👤 {display_name}\n💸 Amount: {amount:.2f}\n📁 Category: {category}\n📝 Note: {description}", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("⚠️ Amount must be a valid number.")

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ Usage: `/inc <amount> <category> [description]`", parse_mode="Markdown")
            return
        amount = float(args[0])
        category = args[1]
        description = " ".join(args[2:]) if len(args) > 2 else "N/A"
        display_name = USER_NAMES.get(user.id, user.first_name)

        conn = sqlite3.connect('cashbook.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (user_id, username, type, amount, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                       (user.id, display_name, 'INCOME', amount, category, description))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ **Income Logged!**\n👤 {display_name}\n💰 Amount: {amount:.2f}\n📁 Category: {category}\n📝 Note: {description}", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("⚠️ Amount must be a valid number.")

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    conn = sqlite3.connect('cashbook.db')
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    if df.empty:
        await update.message.reply_text("ℹ️ No transactions recorded yet.")
        return
    total_income = df[df['type'] == 'INCOME']['amount'].sum()
    total_expense = df[df['type'] == 'EXPENSE']['amount'].sum()
    net_cash_in_hand = total_income - total_expense

    user_summary = ""
    for u_id, name in USER_NAMES.items():
        u_df = df[df['user_id'] == u_id]
        u_inc = u_df[u_df['type'] == 'INCOME']['amount'].sum()
        u_exp = u_df[u_df['type'] == 'EXPENSE']['amount'].sum()
        user_summary += f"\n👤 **{name}**\n  • Income: {u_inc:.2f}\n  • Expense: {u_exp:.2f}\n"

    summary_msg = (
        "📖 **CASH BOOK SUMMARY**\n"
        "---------------------------\n"
        f"💰 **Total Income:** {total_income:.2f}\n"
        f"💸 **Total Expenses:** {total_expense:.2f}\n"
        f"💵 **Cash in Hand:** {net_cash_in_hand:.2f}\n"
        "---------------------------\n"
        "**Individual Breakdown:**"
        f"{user_summary}"
    )
    await update.message.reply_text(summary_msg, parse_mode="Markdown")

async def show_settlement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    conn = sqlite3.connect('cashbook.db')
    df = pd.read_sql_query("SELECT * FROM transactions WHERE type='EXPENSE'", conn)
    conn.close()
    if df.empty:
        await update.message.reply_text("ℹ️ No expenses recorded to calculate settlement.")
        return
    total_expense = df['amount'].sum()
    per_person_share = total_expense / 2.0

    user1_id, user2_id = ALLOWED_USERS[0], ALLOWED_USERS[1]
    u1_name, u2_name = USER_NAMES[user1_id], USER_NAMES[user2_id]
    u1_spent = df[df['user_id'] == user1_id]['amount'].sum()
    u2_spent = df[df['user_id'] == user2_id]['amount'].sum()

    msg = f"🤝 **SETTLEMENT & BALANCE (50/50 Split)**\nTotal Combined Expenses: **{total_expense:.2f}**\nEqual Share: **{per_person_share:.2f}**\n\n"
    msg += f"• **{u1_name}** paid: {u1_spent:.2f}\n• **{u2_name}** paid: {u2_spent:.2f}\n\n"

    diff = u1_spent - per_person_share
    if diff > 0:
        msg += f"⚖️ **{u2_name}** owes **{u1_name}**: **{abs(diff):.2f}**"
    elif diff < 0:
        msg += f"⚖️ **{u1_name}** owes **{u2_name}**: **{abs(diff):.2f}**"
    else:
        msg += "⚖️ Both users are completely even!"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    conn = sqlite3.connect('cashbook.db')
    df = pd.read_sql_query("SELECT id, date, username, type, category, amount, description FROM transactions", conn)
    conn.close()
    if df.empty:
        await update.message.reply_text("ℹ️ No data available to export.")
        return
    file_name = "CashBook_Report.xlsx"
    df.to_excel(file_name, index=False)
    await update.message.reply_document(document=open(file_name, 'rb'), filename=file_name, caption="📁 Here is your full Cash Book report.")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    text = update.message.text
    if text == '📊 Cash Book Summary':
        await show_summary(update, context)
    elif text == '🤝 Settlement Status':
        await show_settlement(update, context)
    elif text == '📥 Export Cash Book':
        await export_excel(update, context)
    elif text == '➕ Add Expense':
        await update.message.reply_text("To add an expense, use:\n`/exp <amount> <category> <description>`", parse_mode="Markdown")
    elif text == '💵 Add Income':
        await update.message.reply_text("To add income, use:\n`/inc <amount> <category> <description>`", parse_mode="Markdown")
    elif text == '❓ Help':
        await start(update, context)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, telegram_app.bot)
    import asyncio
    asyncio.run(telegram_app.process_update(update))
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running live on Render!", 200

def setup_telegram_bot():
    global telegram_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("exp", add_expense))
    telegram_app.add_handler(CommandHandler("inc", add_income))
    telegram_app.add_handler(CommandHandler("summary", show_summary))
    telegram_app.add_handler(CommandHandler("settle", show_settlement))
    telegram_app.add_handler(CommandHandler("export", export_excel))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    loop.run_until_complete(telegram_app.initialize())
    
    if WEBHOOK_URL:
        loop.run_until_complete(telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}"))

if __name__ == "__main__":
    import asyncio
    setup_telegram_bot()
    app.run(host="0.0.0.0", port=PORT)
  
