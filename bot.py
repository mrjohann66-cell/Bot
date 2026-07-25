import sqlite3
import json
import time
import urllib.request
import urllib.parse
import os

# ==========================================
# BOT SOZLAMALARI (CONFIGURATION)
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8865214741:AAGMF3cKcKzm9AgTCIL9T822lH0iJ_fKu6A")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5223776364"))
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
DB_FILE = "bot_database.db"

USER_STATES = {}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            prompt_text TEXT NOT NULL,
            image_url TEXT NOT NULL,
            views_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL,
            invite_link TEXT NOT NULL
        )
    ''')
    
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
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_request("sendMessage", payload)

def send_photo(chat_id, photo, caption, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_request("sendPhoto", payload)

def check_subscriptions(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, title, invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()
    
    if not channels: return True, []
    
    not_subscribed = []
    for ch_id, title, link in channels:
        try:
            res = api_request("getChatMember", {"chat_id": ch_id, "user_id": user_id})
            if res and res.get("ok"):
                status = res["result"].get("status")
                if status not in ["creator", "administrator", "member"]:
                    not_subscribed.append({"title": title, "link": link})
        except Exception: pass
            
    if not_subscribed: return False, not_subscribed
    return True, []

def get_subscription_keyboard(unsub_list):
    inline_keyboard = []
    for ch in unsub_list:
        inline_keyboard.append([{"text": f"📢 {ch['title']}", "url": ch['link']}])
    inline_keyboard.append([{"text": "Tekshirish 🔄", "callback_data": "check_sub"}])
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

def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    first_name = message["from"].get("first_name", "Foydalanuvchi")
    text = message.get("text", "").strip()

    if user_id != ADMIN_ID:
        is_sub, unsub_channels = check_subscriptions(user_id)
        if not is_sub:
            kb = get_subscription_keyboard(unsub_channels)
            send_message(chat_id, "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>", reply_markup=kb)
            return

    state_info = USER_STATES.get(user_id, {})
    current_state = state_info.get("state")

    if text == "/start":
        USER_STATES[user_id] = {"state": "IDLE"}
        send_message(chat_id, f"Salom, <b>{first_name}</b>! 👋

<b>Nano Banana Prompts</b> botiga xush kelibsiz!
Prompt kalit so'zini yozing.", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
        return

    # ADMIN WIZARD
    if user_id == ADMIN_ID:
        if text == "⚙️ Admin Panel" or text == "/admin":
            USER_STATES[user_id] = {"state": "ADMIN_MENU"}
            send_message(chat_id, "👑 <b>Admin Paneliga xush kelibsiz!</b>", reply_markup=get_admin_keyboard())
            return

        if text == "➕ Prompt qo'shish":
            USER_STATES[user_id] = {"state": "WAITING_PROMPT_IMAGE", "data": {}}
            send_message(chat_id, "🖼 <b>Post uchun rasm jo'nating!</b>")
            return

        if current_state == "WAITING_PROMPT_IMAGE":
            photo_url = None
            if "photo" in message:
                photo_url = message["photo"][-1]["file_id"]
            elif text and text.startswith("http"):
                photo_url = text

            if photo_url:
                USER_STATES[user_id]["data"]["image_url"] = photo_url
                USER_STATES[user_id]["state"] = "WAITING_PROMPT_DESCRIPTION"
                send_message(chat_id, "✅ Rasm qabul qilindi!

✏️ <b>Post uchun izoh yozing!</b>")
            return

        if current_state == "WAITING_PROMPT_DESCRIPTION":
            USER_STATES[user_id]["data"]["description"] = text
            USER_STATES[user_id]["state"] = "WAITING_PROMPT_KEYWORD"
            send_message(chat_id, "✅ Izoh qabul qilindi!

🔑 <b>Kalit so'z jo'nating!</b>")
            return

        if current_state == "WAITING_PROMPT_KEYWORD":
            keyword = text.lower().strip().replace(" ", "_")
            USER_STATES[user_id]["data"]["keyword"] = keyword
            USER_STATES[user_id]["state"] = "WAITING_PROMPT_TEXT"
            send_message(chat_id, f"✅ Kalit so'z (<code>{keyword}</code>) qabul qilindi!

📝 <b>Promptni jo'nating!</b>")
            return

        if current_state == "WAITING_PROMPT_TEXT":
            prompt_text = text
            p_data = USER_STATES[user_id]["data"]
            kw, img, desc = p_data["keyword"], p_data["image_url"], p_data.get("description", "AI Prompt")
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO prompts (keyword, prompt_text, image_url, description) VALUES (?, ?, ?, ?)", (kw, prompt_text, img, desc))
            conn.commit(); conn.close()
            USER_STATES[user_id] = {"state": "ADMIN_MENU"}
            send_message(chat_id, f"🎉 <b>Prompt saqlandi!</b>
🔑 Kalit so'z: <code>{kw}</code>
✏️ Izoh: {desc}", reply_markup=get_admin_keyboard())
            return

        if text in ["📋 Kanallar ro'yxati", "❌ Kanalni olib tashlash"]:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id, title FROM channels")
            channels = cursor.fetchall()
            conn.close()
            if not channels:
                send_message(chat_id, "Hali hech qanday majburiy kanal qo'shilmagan.", reply_markup=get_admin_keyboard())
            else:
                msg = "📋 <b>Majburiy kanallar ro'yxati:</b>

Kanalni olib tashlash uchun mos tugmani bosing:"
                inline_keyboard = [
                    [{"text": f"❌ {ch[1]} (O'chirish)", "callback_data": f"del_chan_{ch[0]}"}]
                    for ch in channels
                ]
                send_message(chat_id, msg, reply_markup={"inline_keyboard": inline_keyboard})
            return

        if text == "📢 Majburiy kanal qo'shish":
            USER_STATES[user_id] = {"state": "WAITING_CHANNEL_ADD"}
            send_message(chat_id, (
                "📢 <b>Majburiy kanal qo'shish bo'yicha yo'riqnoma:</b>

"
                "1️⃣ Avvalo botimizni kanalingizga <b>Administrator</b> qilib tayinlang (barcha ruxsatlar bilan).
"
                "2️⃣ So'ngra ushbu kanaldagi <b>istalgan bitta postni (xabarni) ushbu botga forward qiling (uzating)</b> "
                "yoki kanal username-ini (@kanal) / havolasini jo'nating!

"
                "<i>✨ Postni forward qilishingiz bilan kanal avtomatik tarzda aniqlanadi va saqlanadi.</i>"
            ))
            return

        if current_state == "WAITING_CHANNEL_ADD":
            ch_id, title, link = None, None, None
            if "forward_from_chat" in message:
                chat = message["forward_from_chat"]
                ch_id, title = str(chat.get("id", "")), chat.get("title", "Yangi Kanal")
                username = chat.get("username", "")
                link = f"https://t.me/{username}" if username else f"https://t.me/c/{ch_id.replace('-100', '')}/1"
            elif text:
                if text.startswith("@"):
                    username = text.replace("@", "")
                    ch_id, title, link = f"@{username}", f"@{username}", f"https://t.me/{username}"
                elif "t.me/" in text:
                    link = text
                    uName = text.split("t.me/")[-1].replace("/", "")
                    ch_id, title = f"@{uName}", f"Kanal ({uName})"

            if ch_id and title and link:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO channels (channel_id, title, invite_link) VALUES (?, ?, ?)", (ch_id, title, link))
                conn.commit(); conn.close()
                USER_STATES[user_id] = {"state": "ADMIN_MENU"}
                send_message(chat_id, f"🎉 <b>Kanal muvaffaqiyatli saqlandi!</b>
📢 {title}
🆔 {ch_id}", reply_markup=get_admin_keyboard())
            else:
                send_message(chat_id, "❌ Kanal ma'lumotlarini aniqlab bo'lmadi.")
            return

    # SEARCH KEYWORD
    keyword_input = text.lower().strip().replace(" ", "_")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT prompt_text, image_url, views_count FROM prompts WHERE keyword = ?", (keyword_input,))
    result = cursor.fetchone()

    if result:
        prompt_text, image_url, views = result
        cursor.execute("UPDATE prompts SET views_count = views_count + 1 WHERE keyword = ?", (keyword_input,))
        conn.commit()
        conn.close()
        caption = f"🎯 <b>Prompt topildi!</b>

🔑 <b>Kalit so'z:</b> <code>{keyword_input}</code>

📝 <b>Prompt matni (Ustiga bosing):</b>
<code>{prompt_text}</code>"
        res = send_photo(chat_id, image_url, caption)
        if not res or not res.get("ok"):
            photo_post = f'<a href="{image_url}">&#8203;</a>' + caption
            send_message(chat_id, photo_post)
    else:
        conn.close()
        send_message(chat_id, f"❌ '{text}' bo'yicha prompt topilmadi.")

def main():
    print("🍌 Nano Banana Prompts Python Bot ishga tushdi...")
    offset = None
    while True:
        try:
            params = {"timeout": 20}
            if offset: params["offset"] = offset
            updates = api_request("getUpdates", params)
            if updates and updates.get("ok"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        handle_message(update["message"])
        except Exception as e:
            time.sleep(3)

if __name__ == "__main__":
    main()
