import sqlite3
import json
import time
import urllib.request
import urllib.parse
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==========================================
# BOT SOZLAMALARI (CONFIGURATION)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8865214741:AAGMF3cKcKzm9AgTCIL9T822lH0iJ_fKu6A")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5223776364"))
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

DB_FILE = "bot_database.db"

# Admin holatlarini saqlash xotirasi (In-memory FSM)
# user_id -> {"state": "...", "data": {...}}
USER_STATES = {}

# ==========================================
# MA'LUMOTLAR BAZASI (DATABASE SETUP)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Promptlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            prompt_text TEXT NOT NULL,
            image_url TEXT NOT NULL,
            description TEXT DEFAULT 'AI Image Generation Prompt',
            views_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE prompts ADD COLUMN description TEXT DEFAULT 'AI Image Generation Prompt'")
    except Exception:
        pass
    
    # Majburiy kanallar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL,
            invite_link TEXT NOT NULL
        )
    ''')
    
    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# TELEGRAM API YORDAMCHI FUNKSIYALARI
# ==========================================
def api_request(method, data=None):
    url = API_URL + method
    try:
        if data:
            data_bytes = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            res = response.read().decode('utf-8')
            return json.loads(res)
    except Exception as e:
        print(f"[API Xatosi] {method}: {e}")
        return None

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_request("sendMessage", payload)

def send_photo(chat_id, photo, caption, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_request("sendPhoto", payload)

def answer_callback_query(callback_query_id, text, show_alert=False):
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    }
    return api_request("answerCallbackQuery", payload)

# ==========================================
# MAJBURIY A'ZOLIKNI TEKSHIRISH
# ==========================================
def check_subscriptions(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, title, invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()
    
    if not channels:
        return True, []
    
    not_subscribed = []
    for ch_id, title, link in channels:
        try:
            res = api_request("getChatMember", {"chat_id": ch_id, "user_id": user_id})
            if res and res.get("ok"):
                status = res["result"].get("status")
                if status not in ["creator", "administrator", "member"]:
                    not_subscribed.append({"title": title, "link": link})
            else:
                # Agar kanal ID xato bo'lsa yoki bot admin bo'lmasa, o'tkazib yuboramiz
                pass
        except Exception:
            pass
            
    if not_subscribed:
        return False, not_subscribed
    return True, []

def get_subscription_keyboard(unsub_list):
    inline_keyboard = []
    for idx, ch in enumerate(unsub_list):
        inline_keyboard.append([{
            "text": f"📢 {ch['title']}",
            "url": ch['link']
        }])
    inline_keyboard.append([{
        "text": "Tekshirish 🔄",
        "callback_data": "check_sub"
    }])
    return {"inline_keyboard": inline_keyboard}

def get_main_keyboard(is_admin=False):
    keyboard = [
        [{"text": "🔍 Prompt qidirish"}, {"text": "📚 Barcha Promptlar"}],
        [{"text": "ℹ️ Bot haqida"}]
    ]
    if is_admin:
        keyboard.append([{"text": "⚙️ Admin Panel"}])
    return {"keyboard": keyboard, "resize_keyboard": True}

def get_admin_keyboard():
    return {
        "keyboard": [
            [{"text": "➕ Prompt qo'shish"}, {"text": "📊 Statistika"}],
            [{"text": "📢 Majburiy kanal qo'shish"}, {"text": "❌ Kanalni olib tashlash"}],
            [{"text": "📋 Kanallar ro'yxati"}, {"text": "🗑 Prompt o'chirish"}],
            [{"text": "⬅️ Bosh menyu"}]
        ],
        "resize_keyboard": True
    }

# ==========================================
# FOYDALANUVCHILARNI SAQLASH
# ==========================================
def register_user(user_id, first_name, username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
                   (user_id, first_name, username))
    conn.commit()
    conn.close()

# ==========================================
# ASOSIY XABARLARNI QAYTA ISHLASH (HANDLERS)
# ==========================================
def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    first_name = message["from"].get("first_name", "Foydalanuvchi")
    username = message["from"].get("username", "")
    
    register_user(user_id, first_name, username)
    text = message.get("text", "").strip()
    
    # Majburiy a'zolikni tekshirish (Admin bo'lmasa)
    if user_id != ADMIN_ID:
        is_sub, unsub_channels = check_subscriptions(user_id)
        if not is_sub:
            kb = get_subscription_keyboard(unsub_channels)
            send_message(
                chat_id,
                "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>

A'zo bo'lgach <b>'Tekshirish 🔄'</b> tugmasini bosing.",
                reply_markup=kb
            )
            return

    state_info = USER_STATES.get(user_id, {})
    current_state = state_info.get("state")

    # 1. /start buyrug'i
    if text == "/start":
        USER_STATES[user_id] = {"state": "IDLE"}
        welcome = (
            f"Salom, <b>{first_name}</b>! 👋

"
            "<b>Nano Banana Prompts</b> botiga xush kelibsiz!

"
            "Siz bu yerda eng so'nggi va sifatli AI promptlarni topishingiz mumkin.
"
            "Prompt nomini yoki kalit so'zini kiriting (masalan: <code>banana_cyberpunk</code>)."
        )
        send_message(chat_id, welcome, reply_markup=get_main_keyboard(user_id == ADMIN_ID))
        return

    # 2. ADMIN PANELI VIZARDI (PROMPT QO'SHISH V.B.)
    if user_id == ADMIN_ID:
        if text == "⚙️ Admin Panel" or text == "/admin":
            USER_STATES[user_id] = {"state": "ADMIN_MENU"}
            send_message(chat_id, "👑 <b>Admin Paneliga xush kelibsiz!</b>

Kerakli bo'limni tanlang:", reply_markup=get_admin_keyboard())
            return
            
        if text == "⬅️ Bosh menyu":
            USER_STATES[user_id] = {"state": "IDLE"}
            send_message(chat_id, "Bosh menyudasiz.", reply_markup=get_main_keyboard(True))
            return

        # ADMIN STEP 1: Prompt qo'shish tugmasi bosildi -> Rasm so'rash
        if text == "➕ Prompt qo'shish":
            USER_STATES[user_id] = {"state": "WAITING_PROMPT_IMAGE", "data": {}}
            send_message(
                chat_id,
                "🖼 <b>Post uchun rasm jo'nating!</b>

<i>(Foto fayl yuboring yoki rasm havolasini (URL) kiriting)</i>"
            )
            return

        # ADMIN STEP 2: Rasm kelganda -> Izoh so'rash
        if current_state == "WAITING_PROMPT_IMAGE":
            photo_url = None
            if "photo" in message:
                photos = message["photo"]
                photo_url = photos[-1]["file_id"]
            elif text and (text.startswith("http://") or text.startswith("https://")):
                photo_url = text
            
            if photo_url:
                USER_STATES[user_id]["data"]["image_url"] = photo_url
                USER_STATES[user_id]["state"] = "WAITING_PROMPT_DESCRIPTION"
                send_message(
                    chat_id,
                    "✅ Rasm qabul qilindi!

✏️ <b>Post uchun izoh yozing!</b>
<i>(Kanal va foydalanuvchilar postda ko'radigan qisqa izoh/tavsif matni)</i>"
                )
            else:
                send_message(chat_id, "❌ Iltimos, faqat rasm (photo) yoki rasmgacha to'g'ri link jo'nating.")
            return

        # ADMIN STEP 3: Izoh kelganda -> Kalit so'z so'rash
        if current_state == "WAITING_PROMPT_DESCRIPTION":
            USER_STATES[user_id]["data"]["description"] = text
            USER_STATES[user_id]["state"] = "WAITING_PROMPT_KEYWORD"
            send_message(
                chat_id,
                "✅ Izoh qabul qilindi!

🔑 <b>Kalit so'z jo'nating!</b>
<i>(Misol: banana_cyberpunk yoki cyberpunk_1)</i>"
            )
            return

        # ADMIN STEP 4: Kalit so'z kelganda -> Prompt matnini so'rash
        if current_state == "WAITING_PROMPT_KEYWORD":
            keyword = text.lower().strip().replace(" ", "_")
            USER_STATES[user_id]["data"]["keyword"] = keyword
            USER_STATES[user_id]["state"] = "WAITING_PROMPT_TEXT"
            send_message(
                chat_id,
                f"✅ Kalit so'z (<code>{keyword}</code>) qabul qilindi!

📝 <b>Promptni jo'nating!</b>
<i>(To'liq AI prompt matnini yuboring)</i>"
            )
            return

        # ADMIN STEP 5: Prompt matni kelganda -> Saqlash
        if current_state == "WAITING_PROMPT_TEXT":
            prompt_text = text
            p_data = USER_STATES[user_id]["data"]
            keyword = p_data["keyword"]
            image_url = p_data["image_url"]
            description = p_data.get("description", "AI Image Generation Prompt")
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO prompts (keyword, prompt_text, image_url, description) VALUES (?, ?, ?, ?)",
                    (keyword, prompt_text, image_url, description)
                )
                conn.commit()
                conn.close()
                USER_STATES[user_id] = {"state": "ADMIN_MENU"}
                
                success_msg = (
                    "🎉 <b>Prompt muvaffaqiyatli saqlandi va post tayyorlandi!</b>

"
                    f"🔑 <b>Kalit so'z:</b> <code>{keyword}</code>
"
                    f"✏️ <b>Izoh:</b> {description}

"
                    "Endi foydalanuvchilar ushbu kalit so'zni yozganda rasm, izoh va <b>'📋 Promptni nusxalash'</b> tugmasi beriladi!"
                )
                send_message(chat_id, success_msg, reply_markup=get_admin_keyboard())
            except sqlite3.IntegrityError:
                conn.close()
                send_message(chat_id, f"⚠️ <b>'{keyword}'</b> kalit so'zi allaqachon mavjud! Iltimos, qaytadan boshqaring.")
            return

        # ADMIN: Statistika
        if text == "📊 Statistika":
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM prompts")
            prompts_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM channels")
            channels_count = cursor.fetchone()[0]
            conn.close()
            
            stats_msg = (
                "📊 <b>BOT STATISTIKASI</b>

"
                f"👥 Foydalanuvchilar soni: <b>{users_count} ta</b>
"
                f"📝 Promptlar soni: <b>{prompts_count} ta</b>
"
                f"📢 Majburiy kanallar: <b>{channels_count} ta</b>
"
                f"⚙️ Admin ID: <code>{ADMIN_ID}</code>"
            )
            send_message(chat_id, stats_msg, reply_markup=get_admin_keyboard())
            return

        # ADMIN: Majburiy kanal qo'shish
        if text == "📢 Majburiy kanal qo'shish":
            USER_STATES[user_id] = {"state": "WAITING_CHANNEL_ADD"}
            instruction = (
                "📢 <b>Majburiy kanal qo'shish bo'yicha yo'riqnoma:</b>

"
                "1️⃣ Avvalo botimizni kanalingizga <b>Administrator</b> qilib tayinlang (barcha ruxsatlar bilan).
"
                "2️⃣ So'ngra ushbu kanaldagi <b>istalgan bitta postni (xabarni) ushbu botga forward qiling (uzating)</b> "
                "yoki kanal username-ini (@kanal) / havolasini jo'nating!

"
                "<i>✨ Postni forward qilishingiz bilan kanal avtomatik tarzda aniqlanadi va saqlanadi.</i>"
            )
            send_message(chat_id, instruction)
            return

        if current_state == "WAITING_CHANNEL_ADD":
            ch_id = None
            title = None
            link = None

            # 1. Forward qilingan kanal posti bo'lsa
            if "forward_from_chat" in message:
                chat_info = message["forward_from_chat"]
                ch_id = str(chat_info.get("id", ""))
                title = chat_info.get("title", "Yangi Kanal")
                username = chat_info.get("username", "")
                if username:
                    link = f"https://t.me/{username}"
                else:
                    link = f"https://t.me/c/{ch_id.replace('-100', '')}/1"
            
            # 2. Kanal username, linki yoki matn yuborilgan bo'lsa
            elif text:
                clean_text = text.strip()
                if clean_text.startswith("@"):
                    username = clean_text.replace("@", "")
                    # Telegram API getChat orqali kanal ma'lumotini olishga urinish
                    chat_res = api_request("getChat", {"chat_id": f"@{username}"})
                    if chat_res and chat_res.get("ok"):
                        chat_info = chat_res["result"]
                        ch_id = str(chat_info.get("id"))
                        title = chat_info.get("title", username)
                        link = f"https://t.me/{username}"
                    else:
                        ch_id = f"@{username}"
                        title = f"@{username}"
                        link = f"https://t.me/{username}"
                elif "t.me/" in clean_text:
                    link = clean_text
                    username = clean_text.split("t.me/")[-1].replace("/", "")
                    title = f"Kanal ({username})"
                    ch_id = f"@{username}"
                elif "|" in clean_text:
                    parts = clean_text.split("|")
                    ch_id = parts[0].strip()
                    title = parts[1].strip()
                    link = parts[2].strip() if len(parts) > 2 else f"https://t.me/{ch_id.replace('@','')}"

            if ch_id and title and link:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
                               (ch_id, title, link))
                conn.commit()
                conn.close()
                USER_STATES[user_id] = {"state": "ADMIN_MENU"}
                
                success_msg = (
                    "🎉 <b>Kanal muvaffaqiyatli saqlandi va majburiy a'zolikka qo'shildi!</b>

"
                    f"📢 <b>Kanal nomi:</b> {title}
"
                    f"🆔 <b>Kanal ID:</b> <code>{ch_id}</code>
"
                    f"🔗 <b>Havola:</b> {link}

"
                    "Endi foydalanuvchilar ushbu kanalga a'zo bo'lmaguncha botdan foydalana olishmaydi!"
                )
                send_message(chat_id, success_msg, reply_markup=get_admin_keyboard())
            else:
                send_message(chat_id, "❌ Kanal ma'lumotlarini aniqlab bo'lmadi. Iltimos kanaldan bitta postni botga forward (uzatib) qiling yoki @username ko'rinishida jo'nating.")
            return

        # ADMIN: Kanallar ro'yxati & Kanalni olib tashlash
        if text in ["📋 Kanallar ro'yxati", "❌ Kanalni olib tashlash"]:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id, title, invite_link FROM channels")
            channels = cursor.fetchall()
            conn.close()
            
            if not channels:
                send_message(chat_id, "Hali hech qanday majburiy kanal qo'shilmagan.", reply_markup=get_admin_keyboard())
            else:
                msg = "📋 <b>Majburiy kanallar ro'yxati:</b>

Kanalni olib tashlash uchun mos tugmani bosing:

"
                inline_keyboard = []
                for ch in channels:
                    msg += f"• <b>{ch[1]}</b> ({ch[0]})
"
                    inline_keyboard.append([
                        {"text": f"❌ {ch[1]} (O'chirish)", "callback_data": f"del_chan_{ch[0]}"}
                    ])
                
                send_message(chat_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
            return

        # ADMIN: Prompt o'chirish
        if text == "🗑 Prompt o'chirish":
            USER_STATES[user_id] = {"state": "WAITING_DELETE_KEYWORD"}
            send_message(chat_id, "O'chirmoqchi bo'lgan promptning kalit so'zini kiriting:")
            return

        if current_state == "WAITING_DELETE_KEYWORD":
            keyword = text.lower().strip()
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prompts WHERE keyword = ?", (keyword,))
            rows = cursor.rowcount
            conn.commit()
            conn.close()
            USER_STATES[user_id] = {"state": "ADMIN_MENU"}
            if rows > 0:
                send_message(chat_id, f"✅ <b>'{keyword}'</b> prompti o'chirildi!", reply_markup=get_admin_keyboard())
            else:
                send_message(chat_id, f"⚠️ <b>'{keyword}'</b> kalit so'zi topilmadi.", reply_markup=get_admin_keyboard())
            return

    # 3. ODDIY FOYDALANUVCHILAR UCHUN
    if text == "🔍 Prompt qidirish":
        send_message(chat_id, "Iltimos, izlayotgan prompt kalit so'zini yozing (Masalan: <code>banana_cyberpunk</code>):")
        return

    if text == "📚 Barcha Promptlar":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT keyword FROM prompts LIMIT 20")
        prompts = cursor.fetchall()
        conn.close()
        
        if not prompts:
            send_message(chat_id, "Hozircha hech qanday prompt yo'q.")
        else:
            p_list = "
".join([f"• <code>{p[0]}</code>" for p in prompts])
            send_message(chat_id, f"📚 <b>Mavjud Promptlar kalit so'zlari:</b>

{p_list}

<i>Keraklisining ustiga bossangiz nusxa olinadi va jo'natasiz!</i>")
        return

    if text == "ℹ️ Bot haqida":
        send_message(chat_id, "🍌 <b>Nano Banana Prompts Bot</b>

AI va Midjourney promptlarini ulashish uchun rasmiy bot.
Mutlaqo bepul va tezkor!")
        return

    # 4. KALIT SO'Z BO'YICHA PROMPT QIDIRISH
    keyword_input = text.lower().strip().replace(" ", "_")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT prompt_text, image_url, description, views_count FROM prompts WHERE keyword = ?", (keyword_input,))
    result = cursor.fetchone()
    
    if result:
        prompt_text, image_url, description, views = result
        # Ko'rishlar sonini oshirish
        cursor.execute("UPDATE prompts SET views_count = views_count + 1 WHERE keyword = ?", (keyword_input,))
        conn.commit()
        conn.close()
        
        caption = (
            f"📢 <b>{description or 'AI Image Generation Prompt'}</b>

"
            f"🔑 <b>Kalit so'z:</b> <code>{keyword_input}</code>
"
            f"👁 Ko'rishlar: {views + 1}"
        )
        
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📋 Promptni nusxalash", "callback_data": f"copy_{keyword_input}"}]
            ]
        }
        
        # Rasm va Izoh bilan birga jo'natish (Photo Post + Inline Button)
        res = send_photo(chat_id, image_url, caption, reply_markup=reply_markup)
        if not res or not res.get("ok"):
            # Telegram URL-ni sendPhoto orqali qabul qilmasa, HTML rasm preview texnikasi orqali havola matnisiz rasm-post qilib jo'natish
            photo_post = f'<a href="{image_url}">&#8203;</a>' + caption
            send_message(chat_id, photo_post, reply_markup=reply_markup)
    else:
        conn.close()
        send_message(
            chat_id,
            f"❌ <b>'{text}'</b> bo'yicha hech qanday prompt topilmadi.

"
            "Barcha mavjud promptlarni ko'rish uchun <b>'📚 Barcha Promptlar'</b> tugmasini bosing."
        )

# ==========================================
# CALLBACK QUERY HANDLER (TUGMALAR BOSILGANDA)
# ==========================================
def handle_callback(callback):
    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    user_id = callback["from"]["id"]
    data = callback.get("data")
    
    if data and data.startswith("del_chan_"):
        ch_id = data.replace("del_chan_", "")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ? OR title = ?", (ch_id, ch_id))
        conn.commit()
        conn.close()
        answer_callback_query(callback_id, "✅ Kanal majburiy a'zolikdan olib tashlandi!", show_alert=True)
        send_message(
            chat_id,
            f"🎉 <b>Kanal ({ch_id}) muvaffaqiyatli olib tashlandi!</b>

Qolgan kanallarni ko'rish va boshqarish uchun Admin panelidan foydalanishingiz mumkin.",
            reply_markup=get_admin_keyboard()
        )
        return

    if data and data.startswith("copy_"):
        kw = data.replace("copy_", "")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_text FROM prompts WHERE keyword = ?", (kw,))
        res = cursor.fetchone()
        conn.close()
        if res:
            p_text = res[0]
            answer_callback_query(callback_id, "📋 Prompt matni yuborildi! Ustiga bosib nusxalang.")
            send_message(
                chat_id,
                f"📝 <b>Prompt matni (Nusxalash uchun ustiga bosing):</b>

<code>{p_text}</code>"
            )
        else:
            answer_callback_query(callback_id, "❌ Prompt topilmadi!")
        return

    if data == "check_sub":
        is_sub, unsub_channels = check_subscriptions(user_id)
        if is_sub:
            answer_callback_query(callback_id, "✅ Rahmat! Barcha kanallarga a'zo bo'lgansiz.", show_alert=True)
            send_message(
                chat_id,
                "🎉 Rahmat! A'zolik tasdiqlandi. Endi botdan to'liq foydalanishingiz mumkin!",
                reply_markup=get_main_keyboard(user_id == ADMIN_ID)
            )
        else:
            answer_callback_query(callback_id, "❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# ==========================================
# BOTNING ASOSIY TIKLANISH SIKLI (LONG POLLING)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running! (Dummy server for Railway/Render)")
    def log_message(self, format, *args):
        pass # Loglarni yashirish

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('0.0.0.0', port)
    try:
        httpd = HTTPServer(server_address, DummyHandler)
        print(f"🌐 Cloud hostlar (Railway/Render) uchun HTTP server port {port} da ishga tushdi...")
        httpd.serve_forever()
    except Exception as e:
        print(f"HTTP Server xatosi (Agar sizda Node.js server ishlayotgan bo'lsa, bu xatoga e'tibor bermang): {e}")

def main():
    print("="*50)
    print("🍌 Nano Banana Prompts Python Bot ishga tushdi!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print("="*50)
    
    # Cloud hostlar uchun port band qilish (Railway, Render, kabi)
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    offset = None
    while True:
        try:
            params = {"timeout": 20}
            if offset:
                params["offset"] = offset
            
            updates = api_request("getUpdates", params)
            if updates and updates.get("ok"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        handle_message(update["message"])
                    elif "callback_query" in update:
                        handle_callback(update["callback_query"])
                        
        except KeyboardInterrupt:
            print("
Bot to'xtatildi.")
            break
        except Exception as e:
            print(f"Sikl xatosi: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
