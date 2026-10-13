import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import psycopg2
import sqlite3
import pandas as pd
import openpyxl

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

# Initialize database tables on startup
init_db()

# Initialize Telegram Bot application
bot = Bot(token=BOT_TOKEN)
ptb_application = Application.builder().token(BOT_TOKEN).updater(None).build()

def parse_date_from_text(parts):
    """
    Parses date keywords ('today', 'yesterday', or YYYY-MM-DD) from the end of a list of words.
    Defaults to today's date if omitted.
    """
    today = datetime.now()
    target_date = today.strftime('%Y-%m-%d')
    
    if not parts:
        return parts, target_date
        
    last_word = parts[-1].lower()
    if last_word == "today":
        target_date = today.strftime('%Y-%m-%d')
        parts = parts[:-1]
    elif last_word == "yesterday":
        target_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        parts = parts[:-1]
    else:
        try:
            datetime.strptime(last_word, '%Y-%m-%d')
            target_date = last_word
            parts = parts[:-1]
        except ValueError:
            pass
            
    return parts, target_date

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
        await update.message.reply_text("⛔ You are not authorized to use this cashbook bot.")
        return
        
    name = AUTHORIZED_USERS[user_id]
    welcome_text = (
        f"👑 **Welcome {name}**!\n\n"
        "You can now chat naturally or use commands!\n\n"
        "💬 **Natural Examples:**\n"
        "• `5k gold sip` (Automatically logged as expense)\n"
        "• `10k salary received today` (Automatically logged as income)\n"
        "• `250 chai yesterday`\n\n"
        "📌 **Commands:** `/summary`, `/settlement`, `/help`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Cashbook Bot Help Guide**\n\n"
        "Just type naturally! Examples:\n"
        "• `5k gold sip` $\rightarrow$ Logs ₹5,000 expense\n"
        "• `10k freelance received` $\rightarrow$ Logs ₹10,000 income\n"
        "• `800 silver sip yesterday` $\rightarrow$ Logs for yesterday\n\n"
        "Or use commands: `/summary` or `/settlement`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def log_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, tx_type: str):
    user = update.effective_user
    user_id = user.id
    if user_id not in AUTHORIZED_USERS:
        return
    user_name = AUTHORIZED_USERS[user_id]
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Use format: `/exp <amount> <category> <description>`", parse_mode="Markdown")
        return
    try:
        amount = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return
    category = args[1]
    note_parts, tx_date = parse_date_from_text(args[2:])
    note = " ".join(note_parts) if note_parts else "No description"
    
    save_transaction_to_db(tx_date, user_id, user_name, tx_type, amount, category, note)
    emoji = "💸" if tx_type == "exp" else "💰"
    await update.message.reply_text(
        f"✅ **{tx_type.upper()} Recorded!** {emoji}\n📅 {tx_date} | ₹{amount:,.2f} | {category} - {note}",
        parse_mode="Markdown"
    )

async def exp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_command_handler(update, context, "exp")

async def inc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_command_handler(update, context, "inc")

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
    
    for _, row in df.tail(5).iterrows():
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

# Smart Natural Language Message Handler
async def handle_natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in AUTHORIZED_USERS:
        return
        
    user_name = AUTHORIZED_USERS[user_id]
    text = update.message.text.strip()
    
    # Match amount with optional 'k' or 'K' shorthand (e.g. 5k, 10.5K, 500)
    amount_match = re.search(r'\b(\d+(?:\.\d+)?)([kK])?\b', text)
    if not amount_match:
        return  # Not a transaction message, ignore or let other handlers process
        
    raw_num = float(amount_match.group(1))
    multiplier = amount_match.group(2)
    amount = raw_num * 1000 if multiplier and multiplier.lower() == 'k' else raw_num
    
    # Remove amount from text to extract category, note, and date
    start_idx, end_idx = amount_match.span()
    remaining_text = (text[:start_idx] + text[end_idx:]).strip()
    
    parts = remaining_text.split()
    parts, tx_date = parse_date_from_text(parts)
    cleaned_lower = " ".join(parts).lower()
    
    # Auto-detect if it's income or expense based on keywords
    inc_keywords = ["salary", "income", "received", "payout", "earned", "got", "profit", "dividend"]
    tx_type = "inc" if any(kw in cleaned_lower for kw in inc_keywords) else "exp"
    
    # Extract Category and Note
    if parts:
        category = parts[0].capitalize()
        note = " ".join(parts[1:]) if len(parts) > 1 else " ".join(parts)
    else:
        category = "General"
        note = "Natural entry"
        
    # Save to Database
    save_transaction_to_db(tx_date, user_id, user_name, tx_type, amount, category, note)
    
    emoji = "💸" if tx_type == "exp" else "💰"
    type_label = "EXPENSE" if tx_type == "exp" else "INCOME"
    
    await update.message.reply_text(
        f"✅ **Auto-Logged {type_label}!** {emoji}\n\n"
        f"📅 **Date:** {tx_date}\n"
        f"👤 **By:** {user_name}\n"
        f"💵 **Amount:** ₹{amount:,.2f}\n"
        f"🏷️ **Category:** {category}\n"
        f"📝 **Note:** {note}",
        parse_mode="Markdown"
    )

# Register Handlers
ptb_application.add_handler(CommandHandler("start", start_command))
ptb_application.add_handler(CommandHandler("help", help_command))
ptb_application.add_handler(CommandHandler("exp", exp_command))
ptb_application.add_handler(CommandHandler("inc", inc_command))
ptb_application.add_handler(CommandHandler("summary", summary_command))
ptb_application.add_handler(CommandHandler("settlement", settlement_command))

# Catch all normal text messages for smart natural language parsing
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
