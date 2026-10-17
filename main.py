from datetime import datetime, timedelta, timezone
import json
import os
from fpdf import FPDF
from geopy.distance import geodesic
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from supabase import create_client, Client
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- CONFIGURATION ---
BOT_TOKEN = "8797122421:AAEgAW17o-7WvIgHiYe_lxplitnZ_MiSrs0"
COORDINATOR_ID = "7609626589"

# Supabase Credentials
SUPABASE_URL = "https://mkaxuadbmcqvosqckkz.supabase.co"
SUPABASE_KEY = "sb_publishable_aOmVR8ryNBc8KnFFVv4d9Q_5UlolbVS"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Sheets Credentials (ለ PDF ሪፖርት ማጠናቀሪያ)
JSON_FILE = "credentials.json" 

# አስተማሪው የሚገኝበት ቦታ Coordinate እና የሚፈቀደው ርቀት (በሜትር)
TEACHER_LOCATION = (9.1590690, 39.0281169)
ALLOWED_DISTANCE = 100

# --- GOOGLE SHEETS SETUP ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

sheet1 = None
summary_sheet = None

try:
  if os.path.exists(JSON_FILE):
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
  elif "GOOGLE_CREDENTIALS_JSON" in os.environ:
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
  else:
    creds = None

  if creds:
    client = gspread.authorize(creds)
    main_sheet = client.open("Student_Attendance_DB")
    sheet1 = main_sheet.sheet1
    summary_sheet = main_sheet.worksheet("Summary")
    print("Google Sheets successfully connected!")
except Exception as e:
  print(f"Google Sheets Connection Warning: {e}")

NAME, STUDENT_ID, LOCATION, REASON = range(4)
START_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 አዲስ ምዝገባ ጀምር")]], resize_keyboard=True
)


def get_eth_now():
  return datetime.now(timezone(timedelta(hours=3)))


def is_already_registered(telegram_id, session, date_str):
  try:
    response = supabase.table("attendance").select("*").eq("telegram_id", str(telegram_id)).eq("date", date_str).execute()
    for row in response.data:
      if session in row.get("check_out", "") or session in row.get("status", ""):
        return True
  except Exception as e:
    print(f"Supabase Check Error: {e}")
  return False


# --- PDF GENERATOR ---
async def generate_pdf_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.message.from_user.id)
  if user_id != COORDINATOR_ID:
    await update.message.reply_text("ይቅርታ፣ ይህ ትዕዛዝ ለCoordinator ብቻ ነው!")
    return

  if not summary_sheet:
    await update.message.reply_text("⚠️ Google Sheet አልተገናኘም፤ ሪፖርት ማዘጋጀት አልተቻለም።")
    return

  try:
    await update.message.reply_text("📊 ሪፖርቱ እየተዘጋጀ ነው...")
    data = summary_sheet.get_all_values()

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 15, txt="Weekly Student Attendance Report", ln=True, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(190, 10, txt=f"Generated Date: {get_eth_now().strftime('%Y-%m-%d %I:%M %p')}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    headers = ["Student Name", "Days", "Morning", "Afternoon", "Perf %"]
    col_widths = [60, 20, 38, 38, 34]

    for i, h in enumerate(headers):
      pdf.cell(col_widths[i], 10, h, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Arial", size=9)
    for row in data[2:]:
      if len(row) > 0 and row[0].strip() != "" and row[0] != "Full Name":
        pdf.cell(col_widths[0], 10, str(row[0])[:28], border=1)
        pdf.cell(col_widths[1], 10, str(row[1]) if len(row) > 1 else "0", border=1, align="C")

        for i in [3, 4]:
          val = str(row[i]) if len(row) > i else ""
          if "✅" in val or "Present" in val:
            clean_text = "Present"
          elif "⚠️" in val or "Late" in val:
            clean_text = "Off-time"
          elif "❌" in val or "Absent" in val:
            clean_text = "Absent"
          else:
            clean_text = val.encode("ascii", "ignore").decode("ascii")
          pdf.cell(col_widths[i - 1], 10, clean_text, border=1, align="C")

        perf_raw = str(row[7]) if len(row) > 7 else "0"
        clean_perf = perf_raw.replace("%", "").strip() + " %"
        pdf.cell(col_widths[4], 10, clean_perf, border=1, align="C")
        pdf.ln()

    pdf_file = "Weekly_Attendance.pdf"
    pdf.output(pdf_file)
    with open(pdf_file, "rb") as f:
      await context.bot.send_document(
          chat_id=COORDINATOR_ID,
          document=f,
          caption="📊 የሳምንቱ ሪፖርት ተዘጋጅቷል።",
      )
    os.remove(pdf_file)
  except Exception as e:
    await update.message.reply_text(f"ስህተት፦ {e}")


# --- BOT CONVERSATION LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.message.from_user.id)
  now = get_eth_now()
  today_date = now.strftime("%Y-%m-%d")

  current_minutes = now.hour * 60 + now.minute

  if 510 <= current_minutes <= 600:
    session = "Morning"
  elif 820 <= current_minutes <= 900:
    session = "Afternoon"
  else:
    session = "Late/Off-time"

  context.user_data["session"] = session
  if is_already_registered(user_id, session, today_date):
    await update.message.reply_text(
        f"⚠️ ለ{session} ክፍለ ጊዜ ቀድመህ ተመዝግበሃል።",
        reply_markup=START_KEYBOARD,
    )
    return ConversationHandler.END

  try:
    emp_res = supabase.table("employees").select("*").eq("telegram_id", user_id).execute()
    if emp_res.data and len(emp_res.data) > 0:
      emp = emp_res.data[0]
      context.user_data["full_name"] = emp.get("full_Name") or emp.get("full_name")
      context.user_data["student_id"] = emp.get("department", "N/A")
      
      await update.message.reply_text(
          f"ሰላም {context.user_data['full_name']}! እባክህ መገኘቴን አረጋግጥ የሚለውን ተጫን።",
          reply_markup=ReplyKeyboardMarkup(
              [[KeyboardButton("📍 መገኘቴን አረጋግጥ", request_location=True)]],
              resize_keyboard=True,
          ),
      )
      return LOCATION
  except Exception as e:
    print(f"Supabase Employee Check Error: {e}")

  await update.message.reply_text(
      "አዲስ ተማሪ ነህ። ሙሉ ስምህን አስገባ፦", reply_markup=ReplyKeyboardRemove()
  )
  return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["full_name"] = update.message.text
  await update.message.reply_text("የተማሪ ID ቁጥርህን አስገባ፦")
  return STUDENT_ID


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["student_id"] = update.message.text.upper()
  
  user_id = str(update.message.from_user.id)
  try:
    supabase.table("employees").upsert({
        "telegram_id": user_id,
        "full_Name": context.user_data["full_name"],
        "department": context.user_data["student_id"]
    }).execute()
  except Exception as e:
    print(f"Supabase Employee Insert Error: {e}")

  await update.message.reply_text(
      "አሁን ሎኬሽን ላክ፦",
      reply_markup=ReplyKeyboardMarkup(
          [[KeyboardButton("📍 ሎኬሽን ላክ", request_location=True)]],
          resize_keyboard=True,
      ),
  )
  return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_loc = (update.message.location.latitude, update.message.location.longitude)
  distance = geodesic(TEACHER_LOCATION, user_loc).meters
  now, session = get_eth_now(), context.user_data["session"]
  context.user_data["now"] = now

  if distance > ALLOWED_DISTANCE or session == "Late/Off-time":
    await update.message.reply_text(
        f"❌ ርቀት፡ {int(distance)}m ወይም ሰዓት አልፏል። ምክንያት ጻፍ፦"
    )
    return REASON
  return await finalize_attendance(update, context, "Present")


async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
  return await finalize_attendance(update, context, f"Late ({update.message.text})")


async def finalize_attendance(update, context, status):
  user_id = str(update.message.from_user.id)
  now, session = context.user_data["now"], context.user_data["session"]
  date_str = now.strftime("%Y-%m-%d")
  time_str = now.strftime("%I:%M %p")

  try:
    supabase.table("attendance").insert({
        "telegram_id": user_id,
        "date": date_str,
        "check_in": time_str,
        "check_out": session,
        "status": status
    }).execute()
  except Exception as e:
    print(f"Supabase Attendance Insert Error: {e}")

  if sheet1:
    try:
      sheet1.append_row([
          user_id,
          context.user_data["full_name"],
          context.user_data["student_id"],
          f"{date_str} {time_str} ({session})",
          status,
      ])
    except Exception as e:
      print(f"Google Sheet Append Error: {e}")

  if summary_sheet:
    try:
      if context.user_data["full_name"] not in summary_sheet.col_values(1):
        summary_sheet.append_row([context.user_data["full_name"], "1"], value_input_option="USER_ENTERED")
    except Exception as e:
      print(f"Google Sheet Summary Error: {e}")

  await update.message.reply_text(
      f"✅ ተመዝግቧል። ሰዓት፡ {time_str}",
      reply_markup=START_KEYBOARD,
  )
  return ConversationHandler.END


def main():
  app = Application.builder().token(BOT_TOKEN).build()

  app.add_handler(CommandHandler("report", generate_pdf_report))
  app.add_handler(MessageHandler(filters.Regex("^Report$"), generate_pdf_report))

  conv = ConversationHandler(
      entry_points=[
          CommandHandler("start", start),
          MessageHandler(filters.Regex("^🔄 አዲስ ምዝገባ ጀምር$"), start),
      ],
      states={
          NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
          STUDENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id)],
          LOCATION: [MessageHandler(filters.LOCATION, get_location)],
          REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
      },
      fallbacks=[CommandHandler("start", start)],
  )
  app.add_handler(conv)
  print("Attendance Bot with Supabase & Google Sheets is Live...")
  app.run_polling()


if __name__ == "__main__":
  main()
