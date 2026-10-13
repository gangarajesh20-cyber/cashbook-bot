import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from flask import Flask, request
import psycopg2
import sqlite3
import pandas as pd

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8905066918:AAgqTHCrvt47_BOXR16S07Aus3X08YKBC8")
DATABASE_URL = os.environ.get("DATABASE_URL")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Authorized Users Dictionary
AUTHORIZED_USERS = {
    6394258624: "RAJA ( THE GOD )",
    8941572137: "DUMBU (THE DEVIL)"
}

app = Flask(__name__)

# Initialize Database Connection
def get_db_connection():
    if DATABASE_URL:
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    else:
        conn = sqlite3.connect("cashbook.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cashbook (
                id SERIAL PRIMARY KEY,
                date VARCHAR(50),
                user_id BIGINT,
                user_name VARCHAR(50),
                type VARCHAR(20),
                amount REAL,
                category VARCHAR(50),
                note TEXT
            )
        ''')
    else:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cashbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                user_id INTEGER,
                user_name TEXT,
                type TEXT,
                amount REAL,
                category TEXT,
                note TEXT
            )
        ''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

bot = Bot(token=BOT_TOKEN)
ptb_application = Application.builder().token(BOT_TOKEN).updater(None).build()

def parse_date_and_clean_text(text):
    """
    Extracts date ('today', 'yesterday', or 'YYYY-MM-DD') from anywhere in text.
    Defaults to today's date.
    """
    today = datetime.now()
    target_date = today.strftime('%Y-%m-%d')
    
    # Check keywords
    if re.search(r'\byesterday\b', text, re.IGNORECASE):
        target_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        text = re.sub(r'\byesterday\b', '', text, flags=re.IGNORECASE)
    elif re.search(r'\btoday\b', text, re.IGNORECASE):
        target_date = today.strftime('%Y-%m-%d')
        text = re.sub(r'\btoday\b', '', text, flags=re.IGNORECASE)
    else:
        date_match = re.search(r'\b\d{4}-\d{2}-\d{2}\b', text)
        if date_match:
            target_date = date_match.group(0)
            text = text.replace(target_date, '')

    return text.strip(), target_date

def save_transaction_to_db(tx_date, user_id, user_name, tx_type, amount, category, note):
    conn = get_db_connection()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute(
            "INSERT INTO cashbook (date, user_id, user_name, type, amount, category, note) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (tx_date, user_id, user_name, tx_type, amount, category, note)
        )
    else:
        cur.execute(
            "INSERT INTO cashbook (date, user_id, user_name, type, amount, category, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tx_date, user_id, user_name, tx_type, amount, category, note)
        )
    conn.commit()
    cur.close()
    conn.close()

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔ Unauthorized user.")
        return
        
    name = AUTHORIZED_USERS[user_id]
    welcome_text = (
        f"👑 **Welcome {name}**!\n\n"
        "Smart Natural Language Mode Active!\n\n"
        "💬 **Examples you can type directly:**\n"
        "• `Gold sip 200 today`\n"
        "• `Silver sip 800 yesterday`\n"
        "• `5k gold sip`\n"
        "• `10k salary received`\n\n"
        "📊 Use `/summary` or `/settlement` anytime."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Cashbook Bot Help Guide**\n\n"
        "Just type naturally! Examples:\n"
        "• `Gold sip 200 today` $\rightarrow$ ₹200 expense\n"
        "• `10k freelance received` $\rightarrow$ ₹10,000 income\n"
        "• `800 silver sip yesterday` $\rightarrow$ ₹800 expense (yesterday)\n\n"
        "Commands: `/summary` or `/settlement`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM cashbook", conn)
    conn.close()
    
    if df.empty:
        await update.message.reply_text("ℹ️ No transactions recorded yet.")
        return
        
    total_exp = df[df['type'] == 'exp']['amount'].sum()
    total_inc = df[df['type'] == 'inc']['amount'].sum()
    
    summary_msg = (
        f"📊 **Cash Book Summary**\n\n"
        f"💰 **Total Income:** ₹{total_inc:,.2f}\n"
        f"💸 **Total Expenses:** ₹{total_exp:,.2f}\n"
        f"⚖️ **Net Balance:** ₹{(total_inc - total_exp):,.2f}\n\n"
        f"📋 **Recent Transactions:**\n"
    )
    
    for _, row in df.tail(10).iterrows():
        t_emoji = "💸" if row['type'] == 'exp' else "💰"
        summary_msg += f"{t_emoji} `{row['date']}` | **{row['user_name']}** | ₹{row['amount']:,.2f} ({row['category']}) - {row['note']}\n"
        
    await update.message.reply_text(summary_msg, parse_mode="Markdown")

async def settlement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM cashbook", conn)
    conn.close()
    
    if df.empty:
        await update.message.reply_text("ℹ️ No transactions recorded for settlement.")
        return
        
    exp_df = df[df['type'] == 'exp']
    if exp_df.empty:
        await update.message.reply_text("ℹ️ No expenses recorded yet to split.")
        return
        
    total_expense = exp_df['amount'].sum()
    each_share = total_expense / 2
    spent_by_user = exp_df.groupby('user_name')['amount'].sum().to_dict()
    
    settlement_msg = (
        f"🤝 **50/50 Settlement Status**\n\n"
        f"💸 **Total Expenses:** ₹{total_expense:,.2f}\n"
        f"🎯 **Each Person's Share:** ₹{each_share:,.2f}\n\n"
        "👤 **Paid Breakdown:**\n"
    )
    
    for name in AUTHORIZED_USERS.values():
        paid = spent_by_user.get(name, 0.0)
        diff = paid - each_share
        if diff > 0:
            status = f"🟢 Owed ₹{diff:,.2f} back"
        elif diff < 0:
            status = f"🔴 Needs to pay ₹{abs(diff):,.2f}"
        else:
            status = "✨ Fully Settled"
        settlement_msg += f"• **{name}**: Paid ₹{paid:,.2f} ({status})\n"
        
    await update.message.reply_text(settlement_msg, parse_mode="Markdown")

# Robust Natural Language Message Handler
async def handle_natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in AUTHORIZED_USERS:
        return
        
    user_name = AUTHORIZED_USERS[user_id]
    text = update.message.text.strip()
    
    # 1. Parse and remove Date keywords
    text_no_date, tx_date = parse_date_and_clean_text(text)
    
    # 2. Extract Amount (Supports shorthand 'k'/'K' e.g. 5k, 200, 1.5k)
    amount_match = re.search(r'\b(\d+(?:\.\d+)?)([kK])?\b', text_no_date)
    if not amount_match:
        return  # No number found in the message, ignore
        
    raw_num = float(amount_match.group(1))
    multiplier = amount_match.group(2)
    amount = raw_num * 1000 if multiplier and multiplier.lower() == 'k' else raw_num
    
    # Remove amount from text to extract Category & Description
    start_idx, end_idx = amount_match.span()
    remaining_text = (text_no_date[:start_idx] + " " + text_no_date[end_idx:]).strip()
    words = [w for w in remaining_text.split() if w]
    
    # 3. Detect Income vs Expense
    inc_keywords = ["salary", "income", "received", "payout", "earned", "got", "profit", "dividend"]
    full_lower = text.lower()
    tx_type = "inc" if any(kw in full_lower for kw in inc_keywords) else "exp"
    
    # 4. Extract Category and Note
    if words:
        category = words[0].capitalize()
        note = " ".join(words)
    else:
        category = "General"
        note = "Natural entry"
        
    # 5. Save to Database
    save_transaction_to_db(tx_date, user_id, user_name, tx_type, amount, category, note)
    
    emoji = "💸" if tx_type == "exp" else "💰"
    type_label = "EXPENSE" if tx_type == "exp" else "INCOME"
    
    await update.message.reply_text(
        f"✅ **Auto-Logged {type_label}!** {emoji}\n\n"
        f"📅 **Date:** `{tx_date}`\n"
        f"👤 **By:** {user_name}\n"
        f"💵 **Amount:** ₹{amount:,.2f}\n"
        f"🏷️ **Category:** {category}\n"
        f"📝 **Note:** {note}",
        parse_mode="Markdown"
    )

# Register Handlers
ptb_application.add_handler(CommandHandler("start", start_command))
ptb_application.add_handler(CommandHandler("help", help_command))
ptb_application.add_handler(CommandHandler("summary", summary_command))
ptb_application.add_handler(CommandHandler("settlement", settlement_command))

# Handle all plain text messages for smart parsing
ptb_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_natural_message))

# Flask Webhook Route
@app.route("/", methods=["GET"])
def index():
    return "Cashbook Bot is running live with NLP!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run(ptb_application.process_update(update))
    return "OK", 200

if __name__ == "__main__":
    if WEBHOOK_URL:
        webhook_full_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        asyncio.run(bot.set_webhook(url=webhook_full_url))
        logger.info(f"Webhook set to: {webhook_full_url}")
    
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
