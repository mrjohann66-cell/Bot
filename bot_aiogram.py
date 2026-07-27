import asyncio
import logging
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8865214741:AAGMF3cKcKzm9AgTCIL9T822lH0iJ_fKu6A")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5223776364"))
DB_FILE = "bot_database.db"

logging.basicConfig(level=logging.INFO)

# ==========================================
# FSM STATES (ADMIN WIZARD)
# ==========================================
class AdminStates(StatesGroup):
    waiting_prompt_image = State()
    waiting_prompt_description = State()
    waiting_prompt_keyword = State()
    waiting_prompt_text = State()
    waiting_channel = State()
    waiting_delete_keyword = State()

# ==========================================
# KEYBOARDS
# ==========================================
def main_kb(is_admin=False):
    kb = [
        [KeyboardButton(text="🔍 Prompt qidirish"), KeyboardButton(text="📚 Barcha Promptlar")],
        [KeyboardButton(text="ℹ️ Bot haqida")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Prompt qo'shish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📢 Majburiy kanal qo'shish"), KeyboardButton(text="❌ Kanalni olib tashlash")],
            [KeyboardButton(text="📋 Kanallar ro'yxati"), KeyboardButton(text="🗑 Prompt o'chirish")],
            [KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )

# ==========================================
# DATABASE HELPER
# ==========================================
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone:
        res = cursor.fetchone()
    elif fetchall:
        res = cursor.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return res

# ==========================================
# CLOUD HOSTS (Railway/Render) PORT BINDING
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running! (Dummy server for Railway/Render)")
    def log_message(self, format, *args):
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('0.0.0.0', port)
    try:
        httpd = HTTPServer(server_address, DummyHandler)
        print(f"🌐 Cloud hostlar (Railway/Render) uchun HTTP server port {port} da ishga tushdi...")
        httpd.serve_forever()
    except Exception as e:
        print(f"HTTP Server xatosi (Agar sizda Node.js server ishlayotgan bo'lsa, bu xatoga e'tibor bermang): {e}")

# ==========================================
# MAIN BOT LOGIC
# ==========================================
async def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def cmd_start(message: types.Message, state: FSMContext):
        await state.clear()
        user_id = message.from_user.id
        first_name = message.from_user.first_name
        
        # Register user
        db_query("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, first_name), commit=True)

        await message.answer(
            f"Salom, <b>{first_name}</b>! 👋

"
            "<b>Nano Banana Prompts</b> (Aiogram 3) botiga xush kelibsiz!
"
            "Prompt kalit so'zini yozing (masalan: <code>banana_cyberpunk</code>).",
            parse_mode="HTML",
            reply_markup=main_kb(user_id == ADMIN_ID)
        )

    # Admin Panel
    @dp.message(F.text == "⚙️ Admin Panel")
    async def admin_panel(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        await message.answer("👑 <b>Admin Paneliga xush kelibsiz!</b>", parse_mode="HTML", reply_markup=admin_kb())

    # Prompt qo'shish - Step 1: Ask image
    @dp.message(F.text == "➕ Prompt qo'shish")
    async def add_prompt_step1(message: types.Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID:
            return
        await state.set_state(AdminStates.waiting_prompt_image)
        await message.answer("🖼 <b>Post uchun rasm jo'nating!</b>

<i>(Foto fayl yoki Rasm havolasini jo'nating)</i>", parse_mode="HTML")

    # Step 2: Image received -> Ask description
    @dp.message(AdminStates.waiting_prompt_image)
    async def add_prompt_step2(message: types.Message, state: FSMContext):
        photo_id = None
        if message.photo:
            photo_id = message.photo[-1].file_id
        elif message.text and (message.text.startswith("http://") or message.text.startswith("https://")):
            photo_id = message.text

        if photo_id:
            await state.update_data(image_url=photo_id)
            await state.set_state(AdminStates.waiting_prompt_description)
            await message.answer("✅ Rasm qabul qilindi!

✏️ <b>Post uchun izoh yozing!</b>
<i>(Kanal va foydalanuvchilar ko'radigan qisqa izoh matni)</i>", parse_mode="HTML")
        else:
            await message.answer("❌ Iltimos, rasm yoki rasm linkini jo'nating.")

    # Step 3: Description received -> Ask keyword
    @dp.message(AdminStates.waiting_prompt_description)
    async def add_prompt_step3(message: types.Message, state: FSMContext):
        await state.update_data(description=message.text)
        await state.set_state(AdminStates.waiting_prompt_keyword)
        await message.answer("✅ Izoh qabul qilindi!

🔑 <b>Kalit so'z jo'nating!</b>
<i>(Misol: banana_cyberpunk)</i>", parse_mode="HTML")

    # Step 4: Keyword received -> Ask prompt text
    @dp.message(AdminStates.waiting_prompt_keyword)
    async def add_prompt_step4(message: types.Message, state: FSMContext):
        keyword = message.text.lower().strip().replace(" ", "_")
        await state.update_data(keyword=keyword)
        await state.set_state(AdminStates.waiting_prompt_text)
        await message.answer(f"✅ Kalit so'z (<code>{keyword}</code>) qabul qilindi!

📝 <b>Promptni jo'nating!</b>", parse_mode="HTML")

    # Step 5: Prompt text received -> Save to DB
    @dp.message(AdminStates.waiting_prompt_text)
    async def add_prompt_step5(message: types.Message, state: FSMContext):
        prompt_text = message.text
        data = await state.get_data()
        keyword = data["keyword"]
        image_url = data["image_url"]
        description = data.get("description", "AI Image Generation Prompt")
        
        try:
            db_query("INSERT INTO prompts (keyword, prompt_text, image_url, description) VALUES (?, ?, ?, ?)",
                     (keyword, prompt_text, image_url, description), commit=True)
            await state.clear()
            await message.answer(
                f"🎉 <b>Prompt muvaffaqiyatli saqlandi va post tayyorlandi!</b>

🔑 Kalit so'z: <code>{keyword}</code>
✏️ Izoh: {description}",
                parse_mode="HTML",
                reply_markup=admin_kb()
            )
        except Exception as e:
            await message.answer(f"⚠️ Kalit so'z allaqachon mavjud yoki xatolik: {e}")

    # Majburiy kanal qo'shish
    @dp.message(F.text == "📢 Majburiy kanal qo'shish")
    async def add_channel_step1(message: types.Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID:
            return
        await state.set_state(AdminStates.waiting_channel)
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
        await message.answer(instruction, parse_mode="HTML")

    @dp.message(AdminStates.waiting_channel)
    async def add_channel_step2(message: types.Message, state: FSMContext):
        ch_id = None
        title = None
        link = None

        if message.forward_from_chat:
            chat = message.forward_from_chat
            ch_id = str(chat.id)
            title = chat.title or "Yangi Kanal"
            username = chat.username
            link = f"https://t.me/{username}" if username else f"https://t.me/c/{ch_id.replace('-100', '')}/1"
        elif message.text:
            text = message.text.strip()
            if text.startswith("@"):
                username = text.replace("@", "")
                ch_id = f"@{username}"
                title = f"@{username}"
                link = f"https://t.me/{username}"
            elif "t.me/" in text:
                link = text
                username = text.split("t.me/")[-1].replace("/", "")
                title = f"Kanal ({username})"
                ch_id = f"@{username}"

        if ch_id and title and link:
            db_query("INSERT INTO channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
                     (ch_id, title, link), commit=True)
            await state.clear()
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
            await message.answer(success_msg, parse_mode="HTML", reply_markup=admin_kb())
        else:
            await message.answer("❌ Kanal ma'lumotlarini aniqlab bo'lmadi. Kanaldan bitta postni forward qiling yoki @username kiriting.")

    # Channel List / Delete Channel
    @dp.message(F.text.in_({"📋 Kanallar ro'yxati", "❌ Kanalni olib tashlash"}))
    async def list_or_delete_channels(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            return
        rows = db_query("SELECT channel_id, title FROM channels", fetchall=True)
        if not rows:
            await message.answer("Hali hech qanday majburiy kanal qo'shilmagan.", reply_markup=admin_kb())
            return
        
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"❌ {title} (O'chirish)", callback_data=f"del_chan_{ch_id}")]
            for ch_id, title in rows
        ])
        await message.answer(
            "📋 <b>Majburiy kanallar ro'yxati:</b>

Kanalni olib tashlash uchun quyidagi tugmalardan birini bosing:",
            parse_mode="HTML",
            reply_markup=inline_kb
        )

    # Callback handler for Delete Channel
    @dp.callback_query(F.data.startswith("del_chan_"))
    async def process_del_channel_callback(callback: types.CallbackQuery):
        ch_id = callback.data.replace("del_chan_", "")
        db_query("DELETE FROM channels WHERE channel_id = ? OR title = ?", (ch_id, ch_id), commit=True)
        await callback.answer("✅ Kanal majburiy a'zolikdan olib tashlandi!", show_alert=True)
        await callback.message.answer(
            f"🎉 <b>Kanal ({ch_id}) muvaffaqiyatli olib tashlandi!</b>",
            parse_mode="HTML",
            reply_markup=admin_kb()
        )

    # Callback handler for Copy Prompt button
    @dp.callback_query(F.data.startswith("copy_"))
    async def process_copy_prompt_callback(callback: types.CallbackQuery):
        kw = callback.data.replace("copy_", "")
        row = db_query("SELECT prompt_text FROM prompts WHERE keyword = ?", (kw,), fetchone=True)
        if row:
            p_text = row[0]
            await callback.answer("📋 Prompt matni yuborildi! Ustiga bosib nusxalang.", show_alert=False)
            await callback.message.answer(
                f"📝 <b>Prompt matni (Nusxalash uchun ustiga bosing):</b>

<code>{p_text}</code>",
                parse_mode="HTML"
            )
        else:
            await callback.answer("❌ Prompt topilmadi!", show_alert=True)

    # Prompt Search by Keyword
    @dp.message()
    async def handle_keyword_search(message: types.Message):
        keyword = message.text.lower().strip().replace(" ", "_")
        row = db_query("SELECT prompt_text, image_url, description, views_count FROM prompts WHERE keyword = ?", (keyword,), fetchone=True)
        if row:
            prompt_text, image_url, description, views = row
            db_query("UPDATE prompts SET views_count = views_count + 1 WHERE keyword = ?", (keyword,), commit=True)
            
            caption = (
                f"📢 <b>{description or 'AI Image Generation Prompt'}</b>

"
                f"🔑 <b>Kalit so'z:</b> <code>{keyword}</code>
"
                f"👁 Ko'rishlar: {views + 1}"
            )
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Promptni nusxalash", callback_data=f"copy_{keyword}")]
            ])
            
            try:
                await message.answer_photo(photo=image_url, caption=caption, parse_mode="HTML", reply_markup=inline_kb)
            except Exception:
                photo_post = f'<a href="{image_url}">&#8203;</a>' + caption
                await message.answer(photo_post, parse_mode="HTML", reply_markup=inline_kb)
        else:
            await message.answer(f"❌ '{message.text}' bo'yicha prompt topilmadi.")

    print("Aiogram 3 Bot Running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
