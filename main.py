import datetime
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client

# ---------------------------------------------------------
# 1. Configuration & Credentials
# ---------------------------------------------------------
SUPABASE_URL = "https://mkaxuadbmcqvosqckkz.supabase.co"
SUPABASE_KEY = "sb_publishable_aOmVR8ryNBc8KnFFVv4d9Q_5UlolbVS"
BOT_TOKEN = "8797122421:AAEgAW17o-7WvIgHiYe_lxplitnZ_MiSrs0"
SPREADSHEET_NAME = "Employee Attendance Tracker"

# Supabase Client ማዘጋጀት
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Sheets Client ማዘጋጀት
# credentials.json ፋይል በፕሮጀክቱ ፎልደር ውስጥ ሊኖር ይገባል፤ 
# ወይም በ Environment Variable GOOGLE_CREDENTIALS_JSON መልክ መጫን ይቻላል።
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_gspread_client():
    if os.path.exists("credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    elif "GOOGLE_CREDENTIALS_JSON" in os.environ:
        creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        raise FileNotFoundError("Neither 'credentials.json' file nor 'GOOGLE_CREDENTIALS_JSON' env var found!")
    return gspread.authorize(creds)

try:
    gc = get_gspread_client()
    sheet = gc.open(SPREADSHEET_NAME).sheet1
    print("Google Sheets successfully connected!")
except Exception as e:
    sheet = None
    print(f"Warning: Could not connect to Google Sheets ({e})")

# ---------------------------------------------------------
# 2. Telegram Bot Handlers
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📌 Check In (ግባ)", callback_data="check_in")],
        [InlineKeyboardButton("🚪 Check Out (ውጣ)", callback_data="check_out")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ሰላም {user.first_name}! ወደ ሰራተኛ አቴንዳንስ ሲስተም እንኳን ደህና መጡ።\n\n"
        "ከታች ያሉትን ቁልፎች በመጫን የመግቢያና የመውጫ ሰዓትዎን ይመዝግቡ፡",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    telegram_id = str(user.id)
    
    now = datetime.datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    if query.data == "check_in":
        # -----------------------------------------------------
        # A. Supabase - Save Check In
        # -----------------------------------------------------
        data = {
            "telegram_id": telegram_id,
            "date": current_date,
            "check_in": current_time,
            "check_out": "",
            "status": "Present"
        }
        try:
            supabase.table("attendance").insert(data).execute()
        except Exception as e:
            print(f"Supabase Insert Error: {e}")

        # -----------------------------------------------------
        # B. Google Sheets - Add Row
        # -----------------------------------------------------
        if sheet:
            try:
                sheet.append_row([telegram_id, current_date, current_time, "", "Present"])
            except Exception as e:
                print(f"Google Sheet Append Error: {e}")

        await query.edit_message_text(text=f"✅ በተሳካ ሁኔታ Check-In አድርገዋል!\n📅 ቀን፡ {current_date}\n⏰ ሰዓት፡ {current_time}")

    elif query.data == "check_out":
        # -----------------------------------------------------
        # A. Supabase - Update Check Out
        # -----------------------------------------------------
        try:
            update_data = {"check_out": current_time}
            supabase.table("attendance").update(update_data).eq("telegram_id", telegram_id).eq("date", current_date).execute()
        except Exception as e:
            print(f"Supabase Update Error: {e}")

        # -----------------------------------------------------
        # B. Google Sheets - Update Cell
        # -----------------------------------------------------
        if sheet:
            try:
                # በቴሌግራም ID እና በቀኑ መሰረት ረድፉን (Row) መፈለግ
                cell_list = sheet.findall(telegram_id)
                target_row = None
                for cell in reversed(cell_list):
                    row_date = sheet.cell(cell.row, 2).value
                    if row_date == current_date:
                        target_row = cell.row
                        break
                
                if target_row:
                    sheet.update_cell(target_row, 4, current_time) # Column 4 = Check Out
                else:
                    # ካልተገኘ በአዲስ መስመር ማስገባት
                    sheet.append_row([telegram_id, current_date, "", current_time, "Present"])
            except Exception as e:
                print(f"Google Sheet Update Error: {e}")

        await query.edit_message_text(text=f"🚪 በተሳካ ሁኔታ Check-Out አድርገዋል!\n📅 ቀን፡ {current_date}\n⏰ ሰዓት፡ {current_time}")

# ---------------------------------------------------------
# 3. Main Function
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 የቴሌግራም ቦቱ በስኬት ስራ ጀምሯል...")
    app.run_polling()

if __name__ == "__main__":
    main()
