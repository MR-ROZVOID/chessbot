import asyncio
import json
import ast
import os
import requests
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
import time

# ===== إعدادات البوت =====
TELEGRAM_BOT_TOKEN = "8194404224:AAHjToaPPTMZh4o1Fg_8ZDo0r4zEnAKOPWQ"
ALLOWED_CHAT_ID = 8129954853

# ===== إعداد الهيدرز =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json"
}


# ===== ذاكرة مؤقتة لحفظ اسم المستخدم =====
chat_usernames = {}
waiting_for_username = set()
waiting_for_file = set()

# ===== دوال Chess.com =====
def get_chess_archives(username: str):
    url = f"https://api.chess.com/pub/player/{username}/games/archives"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    return resp.json().get("archives", [])

def get_game_ids_from_archives(archives):
    ids, links = [], []
    for aurl in archives:
        resp = requests.get(aurl, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            continue
        data = resp.json()
        for g in data.get("games", []):
            url = g.get("url")
            if url:
                ids.append(url.split("/")[-1])
                links.append(url)
    return ids, links

def save_list_to_file(lines, filename):
    p = Path(filename)
    with p.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return p.resolve()

# ===== دالة لوحة الأزرار =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎯 تعيين اسم المستخدم", callback_data="set_username")],
        [InlineKeyboardButton("♟️ جلب Game IDs", callback_data="fetch_ids")],
        [InlineKeyboardButton("📊 تحليل المباريات", callback_data="analyze_games")],
        [InlineKeyboardButton("➕ أضف حساب تحليل جديد", callback_data="upload_cookie_file")],

        [InlineKeyboardButton("❌ إلغاء / خروج", callback_data="cancel")]
        
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== دوال التحكم =====
def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id
        if chat_id != ALLOWED_CHAT_ID:
            await context.bot.send_message(chat_id, "🚫 ليس لديك صلاحية لاستخدام هذا البوت.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
USER_FILE = r"\users.json"

def load_users():
    """تحميل المستخدمين من ملف JSON"""
    try:
        with open(USER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"📂 تم تحميل {len(data)} مستخدم من {USER_FILE}")
            return {int(k): v for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_users():
    """حفظ المستخدمين في ملف JSON"""
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_usernames, f, ensure_ascii=False, indent=2)


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 أهلاً بك! استخدم الأزرار للتحكم في البوت:",
        reply_markup=main_menu()
    )

@restricted
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "set_username":
        waiting_for_username.add(chat_id)
        await query.message.reply_text("🧩 أرسل لي اسم المستخدم في Chess.com الآن:")
    elif query.data == "fetch_ids":
        await fetch_games(update, context, ids_only=True)
    elif query.data == "analyze_games":
        await analyze_games(update, context)
    elif query.data == "upload_cookie_file":
        waiting_for_file.add(chat_id)
        await bot.send_message(chat_id, "📤 أرسل الآن الملف النصي (.txt) الذي تريد حفظه:")


    elif query.data == "cancel":
        await query.message.reply_text("✅ تم الإلغاء. اكتب /start للعودة للقائمة.")
@restricted
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in waiting_for_file:
        doc = update.message.document

        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("⚠️ الرجاء إرسال ملف نصي فقط (.txt)")
            return

        # تحميل الملف من تيليجرام
        file = await doc.get_file()
        save_path = os.getcwd()
        file_path = os.path.join(save_path, doc.file_name)

        # التأكد من وجود المجلد
        
        os.makedirs(save_path, exist_ok=True)
        await file.download_to_drive(file_path)

        waiting_for_file.remove(chat_id)
        
        with open(r"raw_token.txt", "r", encoding="utf-8") as f:
            RAW_COOKIES = f.read()
        NEW_COOKIES =[]
        for pair in RAW_COOKIES.split(";"):
            if "=" in pair:
                name, value = pair.strip().split("=", 1)
                NEW_COOKIES.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".chess.com",
                    "path": "/"
                })
        with open(r"token.txt", "w", encoding="utf-8") as f:
            f.write(str(NEW_COOKIES))
        
        # حفظ الملف
        
        


        

        await update.message.reply_text(
            f"✅ تم حفظ الملف بنجاح في:\n`{file_path}`",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text("📎 أرسل ملفًا فقط بعد اختيار '📁 إضافة جديدة' من القائمة.")
@restricted
async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in waiting_for_username:
        username = update.message.text.strip().lower()
        chat_usernames[chat_id] = username
        waiting_for_username.remove(chat_id)
        save_users()  # ✅ نحفظ الاسم في الملف فوراً
        await update.message.reply_text(
            f"✅ تم تعيين اسم المستخدم إلى: {username}",
            reply_markup=main_menu()
        )
@restricted
async def fetch_games(update: Update, context: ContextTypes.DEFAULT_TYPE, ids_only=True):
    chat_id = update.effective_chat.id
    username = chat_usernames.get(chat_id)
    bot = context.bot

    if not username:
        await bot.send_message(chat_id, "❗ لم يتم تعيين اسم المستخدم بعد. اضغط على 🎯 لتعيينه.")
        return

    msg = await bot.send_message(chat_id, "🔍 جارٍ جلب البيانات من Chess.com ...")
    try:
        loop = asyncio.get_running_loop()
        archives = await loop.run_in_executor(None, get_chess_archives, username)
        if not archives:
            await bot.send_message(chat_id, "⚠️ لا توجد أرشيفات متاحة.")
            return

        ids, links = await loop.run_in_executor(None, get_game_ids_from_archives, archives)
        if not ids:
            await bot.send_message(chat_id, "⚠️ لا توجد مباريات مكتملة بعد.")
            return

        if ids_only:
            filename = r"ALL_GAMES.txt"
            filepath = await loop.run_in_executor(None, save_list_to_file, ids, filename)
        

        with open(filepath, "rb") as f:
            await bot.send_document(chat_id, f, filename=filename)

        await bot.send_message(chat_id, f"✅ تم إرسال الملف {filename}", reply_markup=main_menu())

    except Exception as e:
        await bot.send_message(chat_id, f"❌ حدث خطأ أثناء الجلب:\n{e}")
@restricted
async def analyze_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = chat_usernames.get(chat_id)
    bot = context.bot

    if not username:
        await bot.send_message(chat_id, "❗ لم يتم تعيين اسم المستخدم بعد. اضغط على 🎯 لتعيينه.")
        return

    msg = await bot.send_message(chat_id, "📊 جارٍ تحليل مبارياتك ...")
    try:
        while True:
            with open(r"token.txt", "r", encoding="utf-8") as f:
                content = f.read()

            COOKIES = ast.literal_eval(content)
            GAMES = r"GAMES.txt"
            with open(GAMES, "r", encoding="utf-8") as f:
                lines = f.readlines()
        
            if not lines:
                print("تم نقل كل الأسطر، الملف فارغ الآن.")
                break
            game_id = lines[0].strip()
            
            GAME_REVIEW_URL = f"https://www.chess.com/analysis/game/live/{game_id}/review?full=1"
            

            done_games = r'data\done_games.txt'
            with open(done_games, "a", encoding="utf-8") as out:
                out.write(game_id + "\n")
            
            with open(GAMES, "w", encoding="utf-8") as f:
                f.writelines(lines[1:])

            ########
            def send_telegram(token, chat_id, message):
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {"chat_id": chat_id, "text": message}
                try:
                    r = requests.post(url, data=payload, timeout=10)
                    if r.status_code == 200:
                        print("[نجاح] تم إرسال رسالة التليجرام.")
                        return True
                    else:
                        print("[خطأ] فشل إرسال التليجرام:", r.status_code, r.text)
                        return False
                except Exception as e:
                    print("[خطأ] استثناء أثناء إرسال التليجرام:", e)
                    return False
            from webdriver_manager.chrome import ChromeDriverManager
            def start_driver():
                options = webdriver.ChromeOptions()
                options.add_argument("--headless")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                return driver
            def add_cookies(driver, cookies):
                driver.get("https://www.chess.com")
                for c in cookies:
                    try:
                        driver.add_cookie(c)
                    except Exception as e:
                        print(f"تحذير: لم أستطع إضافة cookie {c.get('name')}: {e}")
            def extract_tallies(driver):
                """يستخرج فقط بيانات Brilliant من صفحة التحليل"""
                tallies = {}
                try:
                    # البحث فقط عن عنصر Brilliant
                    row = driver.find_element(By.CSS_SELECTOR, 'div.tallies-new-row[data-cy="tallies-row-Brilliant"]')
                    label = "brilliant"
                    value = row.text.strip() or "0"
                    tallies[label] = value
                except Exception as e:
                    print(f"⚠️ لم يتم العثور على عنصر Brilliant: {e}")
                    tallies["brilliant"] = "0"
                return tallies
            def main():
                driver = start_driver()
                add_cookies(driver, COOKIES)
                driver.get(GAME_REVIEW_URL)
                time.sleep(9)  # ننتظر تحميل الصفحة بالكامل

                tallies = extract_tallies(driver)
                print("\n📊 أنواع الحركات التي لعبتها:\n")
                for k, v in tallies.items():
                    print(f"{k:12s} : {v}")
                if "brilliant" in tallies:
                    try:
                        # في بعض الحالات تكون القيمة مثل "0\n2" فنأخذ أول رقم أو أكبر رقم
                        values = [int(x) for x in tallies["brilliant"].split() if x.isdigit()]
                        if any(v > 0 for v in values):
                            message = f"🎉 Found Brilliant in this game.\nLink: {GAME_REVIEW_URL}"
                            TELEGRAM_CHAT_ID = "8129954853"
                            send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
                    except Exception as e:
                        print(f"حدث خطأ أثناء تحليل قيمة Brilliant: {e}")
                print("\nانتهى التحليل ✅")
                driver.quit()
                
                
            if __name__ == "__main__":
                main()

        
            
                

        text = "DONE"
        await bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode="Markdown")

    except Exception as e:
        await bot.send_message(chat_id, f"❌ حدث خطأ أثناء التحليل:\n{e}")
@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in waiting_for_username:
        await receive_username(update, context)
    else:
        await update.message.reply_text("🤖 استخدم الأزرار للتحكم في البوت.", reply_markup=main_menu())

# ===== التشغيل =====
def main():
    global chat_usernames
    chat_usernames = load_users()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))


    print("🤖 البوت يعمل الآن مع واجهة أزرار...")
    app.run_polling()

if __name__ == "__main__":
    main()
