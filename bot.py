import asyncio
import logging
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)

from database import Database

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8860831492:AAEOr3wpiE5KJTV3oHQ3DgpQ_CK6S1MpSxk")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6237680057"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# ----------------- FSM STATES -----------------
class AddVideoSG(StatesGroup):
    photo = State()
    caption = State()
    current_quality = State()
    video_file = State()
    more_qualities = State()
    price = State()
    code = State()

class BuyVideoSG(StatesGroup):
    wait_screenshot = State()

class BuyVipSG(StatesGroup):
    select_plan = State()
    wait_screenshot = State()

class BroadcastSG(StatesGroup):
    wait_message = State()

class ChangeCardSG(StatesGroup):
    wait_card = State()

class ChangeVipPriceSG(StatesGroup):
    select_plan = State()
    wait_price = State()

class DeleteVideoSG(StatesGroup):
    wait_code = State()

# ----------------- KEYBOARD HELPERS -----------------
def get_user_main_keyboard(is_vip: bool = False):
    kb = []
    if not is_vip:
        kb.append(KeyboardButton(text="👑 VIP olish"))
    kb.append(KeyboardButton(text="🎬 Sotib olgan videolarim"))
    
    return ReplyKeyboardMarkup(
        keyboard=[kb],
        resize_keyboard=True
    )

def get_admin_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Video qo‘shish"), KeyboardButton(text="🗑 Video o'chirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Xabar yuborish")],
            [KeyboardButton(text="💳 Karta raqam almashtirish"), KeyboardButton(text="💎 VIP narxlarini o'zgartirish")]
        ],
        resize_keyboard=True
    )

# ----------------- COMMAND HANDLERS -----------------
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""
    
    db.add_user(user_id, username, full_name)

    if user_id == ADMIN_ID:
        await message.answer(
            "Salom xo'jayin hush kelibsiz, ishni boshlaymizmi?",
            reply_markup=get_admin_main_keyboard()
        )
    else:
        is_vip = db.is_user_vip(user_id)
        status_text = "\n\n👑 <b>Siz VIP a'zosiz!</b> Barcha videolar ochiq." if is_vip else ""
        await message.answer(
            f"Assalomu alaykum! Video kodini kiriting (masalan: 101):{status_text}",
            reply_markup=get_user_main_keyboard(),
            parse_mode="HTML"
        )

# ----------------- BACK / MAIN MENU -----------------
@dp.message(F.text == "⬅️ Bosh menyu")
async def btn_back_main(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        kb = get_admin_main_keyboard()
    else:
        is_vip = db.is_user_vip(user_id)
        kb = get_user_main_keyboard(is_vip)
    await message.answer("Bosh menyudasiz.", reply_markup=kb)

# ----------------- MY PURCHASES -----------------
@dp.message(F.text == "🎬 Sotib olgan videolarim")
async def btn_my_videos(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    purchases = db.get_user_purchased_videos(user_id)
    if not purchases:
        await message.answer("Siz hali birorta ham video xarid qilmadingiz.", reply_markup=get_user_main_keyboard(db.is_user_vip(user_id)))
        return

    text = "🎬 <b>Siz sotib olgan videolar ro'yxati:</b>\n\n"
    for p in purchases:
        text += f"🔹 <b>Kodi:</b> <code>{p[0]}</code> - {p[1][:30]}... ({p[2]:,} so'm)\n"
    text += "\n<i>Videoni ko'rish uchun uning kodini chatga yuboring.</i>"
    await message.answer(text, reply_markup=get_user_main_keyboard(db.is_user_vip(user_id)), parse_mode="HTML")

# ----------------- VIP BUTTON & PROCESS -----------------
@dp.message(F.text == "👑 VIP olish")
async def btn_vip(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if db.is_user_vip(user_id):
        await message.answer("✅ Sizda allaqachon faol VIP obuna mavjud!")
        return
    
    v1w = db.get_setting("vip_1w", "10000")
    v1m = db.get_setting("vip_1m", "25000")
    v6m = db.get_setting("vip_6m", "50000")

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"1 Haftalik - {int(v1w):,} so'm")],
            [KeyboardButton(text=f"1 Oylik - {int(v1m):,} so'm")],
            [KeyboardButton(text=f"6 Oylik - {int(v6m):,} so'm")],
            [KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )
    await state.set_state(BuyVipSG.select_plan)
    await message.answer(
        "VIP tarifini sotib olsangiz barcha videolarni cheklovsiz ko'rishingiz mumkin!\nTarifni tanlang:",
        reply_markup=kb
    )

@dp.message(BuyVipSG.select_plan)
async def process_vip_plan(message: Message, state: FSMContext):
    text = message.text
    if text == "⬅️ Bosh menyu":
        await btn_back_main(message, state)
        return

    card = db.get_setting("card_number", "9860 3501 4870 6350")
    v1w = int(db.get_setting("vip_1w", "10000"))
    v1m = int(db.get_setting("vip_1m", "25000"))
    v6m = int(db.get_setting("vip_6m", "50000"))

    plan = ""
    amount = 0

    if "1 Haftalik" in text:
        plan, amount = "1_week", v1w
    elif "1 Oylik" in text:
        plan, amount = "1_month", v1m
    elif "6 Oylik" in text:
        plan, amount = "6_month", v6m
    else:
        await message.answer("Iltimos, tugmalardan birini tanlang!")
        return

    await state.update_data(vip_plan=plan, amount=amount)
    await state.set_state(BuyVipSG.wait_screenshot)

    await message.answer(
        f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
        f"Karta raqami: <code>{card}</code>\n"
        f"To'lov summasi: <b>{amount:,} so'm</b>\n\n"
        f"To'lovni amalga oshirib, chek (skrinshot) rasmini ushbu chatga yuboring:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Bosh menyu")]], resize_keyboard=True)
    )

@dp.message(BuyVipSG.wait_screenshot, F.photo)
async def process_vip_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id

    payment_id = str(uuid.uuid4())[:8]
    db.create_pending_payment(
        payment_id=payment_id,
        user_id=user_id,
        payment_type="vip",
        vip_plan=data.get("vip_plan", "1_month"),
        amount=data.get("amount", 0)
    )

    await state.clear()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting...", reply_markup=get_user_main_keyboard(db.is_user_vip(user_id)))

    # Send to admin
    plan_names = {"1_week": "1 Haftalik", "1_month": "1 Oylik", "6_month": "6 Oylik"}
    plan_str = plan_names.get(data.get("vip_plan"), "VIP")

    ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_vip_{payment_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"decline_vip_{payment_id}")
            ]
        ]
    )

    user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"👑 <b>Yangi VIP Obuna So'rovi!</b>\n\n👤 Foydalanuvchi: {user_info}\nTarif: <b>{plan_str}</b>\nSumma: <b>{data.get('amount', 0):,} so'm</b>",
        reply_markup=ikb,
        parse_mode="HTML"
    )


# ----------------- VIDEO CODE SEARCH -----------------
@dp.message(F.text.regexp(r'^\d+$'), default_state)
async def handle_video_code(message: Message, state: FSMContext):
    code = message.text.strip()
    video = db.get_video_by_code(code)
    
    if not video:
        await message.answer("⚠️ Bunday kodli video topilmadi!")
        return

    user_id = message.from_user.id
    is_vip = db.is_user_vip(user_id)
    has_bought = db.has_user_bought_video(user_id, code)

    if not is_vip and not has_bought:
        price = video[3]
        await state.set_state(BuyVideoSG.wait_screenshot)
        await state.update_data(buy_video_code=code, buy_video_price=price)
        
        card = db.get_setting("card_number", "9860 3501 4870 6350")
        text = (
            f"🎬 Siz tanlagan video: <b>#{code}</b>
"
            f"💰 Narxi: <b>{price:,} so'm</b>

"
            f"Karta raqami: <code>{card}</code>
"
            f"Iltimos, to'lovni amalga oshiring va chekni rasm ko'rinishida yuboring."
        )
        await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Bosh menyu")]], resize_keyboard=True), parse_mode="HTML")
        return
        
    qualities = db.get_video_files(code)
    if not qualities:
        await message.answer("Ushbu videoning fayllari topilmadi.")
        return

    ikb = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for q in qualities:
        row.append(InlineKeyboardButton(text=q[0], callback_data=f"getvid_{code}_{q[0]}"))
        if len(row) == 2:
            ikb.inline_keyboard.append(row)
            row = []
    if row:
        ikb.inline_keyboard.append(row)

    await message.answer("🎥 Videoni ko'rish uchun sifatni tanlang:", reply_markup=ikb)

@dp.callback_query(F.data.startswith("getvid_"))
async def process_getvid(callback: CallbackQuery):
    _, code, qual = callback.data.split("_")
    video = db.get_video_by_code(code)
    qualities = db.get_video_files(code)
    
    file_id = None
    for q in qualities:
        if q[0] == qual:
            file_id = q[1]
            break
            
    if not file_id:
        await callback.answer("Fayl topilmadi!", show_alert=True)
        return
        
    caption = video[2] if video and video[2] else ""
    await callback.message.answer_video(video=file_id, caption=caption)
    await callback.answer()

# ----------------- MAIN RUN -----------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())