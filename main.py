import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client

# የእርስዎ የ Supabase መረጃዎች
SUPABASE_URL = "https://mkaxuadbmcqvosqckkz.supabase.co"
SUPABASE_KEY = "sb_publishable_aOmVR8ryNBc8KnFFVv4d9Q_5UlolbVS"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# /start ትእዛዝ ሲሰጥ የሚሰራ ሎጂክ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📌 Check In (ግባ)", callback_data="check_in")],
        [InlineKeyboardButton("🚪 Check Out (ውጣ)", callback_data="check_out")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ሰላም {user.first_name}! ወደ ሰራተኛ አቴንዳንስ ሲስተም እንኳን ደህና መጡ። ከታች ያሉትን ቁልፎች በመጫን መግቢያና መውጫዎን ይመዝግቡ፡",
        reply_markup=reply_markup
    )

# ቁልፎች ሲጫኑ የሚሰሩ ስራዎች (Button Handlers)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    telegram_id = str(user.id)
    
    now = datetime.datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    if query.data == "check_in":
        # መረጃውን ወደ attendance ቴብል መላክ
        data = {
            "telegram_id": telegram_id,
            "date": current_date,
            "check_in": current_time,
            "check_out": "",
            "status": "Present"
        }
        supabase.table("attendance").insert(data).execute()
        await query.edit_message_text(text=f"✅ በተሳካ ሁኔታ Check-In አድርገዋል! ሰዓት፡ {current_time}")

    elif query.data == "check_out":
        # Check-out ሰዓቱን ማዘመን
        update_data = {"check_out": current_time}
        supabase.table("attendance").update(update_data).eq("telegram_id", telegram_id).eq("date", current_date).execute()
        await query.edit_message_text(text=f"🚪 በተሳካ ሁኔታ Check-Out አድርገዋል! ሰዓት፡ {current_time}")

def main():
    # የእርስዎ የቴሌግራም ቦት ቶከን
    TOKEN = "8797122421:AAEgAW17o-7WvIgHiYe_lxplitnZ_MiSrs0"
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("ቦቱ በመሥራት ላይ ነው...")
    app.run_polling()

if __name__ == "__main__":
    main()