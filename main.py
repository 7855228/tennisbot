import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import asyncio

API_TOKEN = os.getenv("API_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

CATEGORY_LIMITS = {
    "Gentlemen’s Amateur": 24,
    "Gentlemen’s Challenger": 12,
    "Gentlemen’s Master": 12,
    "Ladies Amateur": 12,
    "Ladies Challenger": 12,
    "Ladies Master": 12,
    "Mixed Amateur": 12,
    "Mixed Master": 12,
    "Gentlemen’s Doubles": 12,
    "Ladies’ Doubles": 12
}
PAIR_CATEGORIES = [
    "Mixed Amateur", "Mixed Master",
    "Gentlemen’s Doubles", "Ladies’ Doubles"
]

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.prod.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Все заявки")
except Exception as e:
    logging.error("❌ Ошибка подключения к Google Таблице:", e)
    sheet = None

class Form(StatesGroup):
    category = State()
    name = State()
    partner = State()
    confirmation = State()
    payment = State()

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer("🎾 Добро пожаловать на теннисный турнир ДРУГ 2025!
Выберите категорию участия:",
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                             *[types.KeyboardButton(c) for c in CATEGORY_LIMITS.keys()]
                         ))
    await Form.category.set()

@dp.message_handler(state=Form.category)
async def process_category(message: types.Message, state: FSMContext):
    category = message.text
    if category not in CATEGORY_LIMITS:
        return await message.reply("Пожалуйста, выберите категорию из списка.")
    await state.update_data(category=category)
    await message.answer("Введите ваше ФИО:")
    await Form.next()

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    data = await state.get_data()
    if data["category"] in PAIR_CATEGORIES:
        await message.answer("Введите ФИО вашего партнёра:")
        await Form.next()
    else:
        await state.update_data(partner="-")
        await ask_slot_availability(message, state)

@dp.message_handler(state=Form.partner)
async def process_partner(message: types.Message, state: FSMContext):
    await state.update_data(partner=message.text)
    await ask_slot_availability(message, state)

async def ask_slot_availability(message, state):
    data = await state.get_data()
    category = data["category"]
    registered = len([row for row in sheet.get_all_records() if row.get("Категория") == category])
    if registered < CATEGORY_LIMITS[category]:
        await message.answer("✅ В категории есть места. Зарегистрироваться в основную сетку?",
                             reply_markup=yes_no_kb())
    else:
        await message.answer("❌ Основная сетка заполнена. Хотите записаться в лист ожидания?",
                             reply_markup=yes_no_kb())
    await Form.confirmation.set()

@dp.message_handler(state=Form.confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "нет"]:
        return await message.answer("Пожалуйста, ответьте 'Да' или 'Нет'")
    data = await state.get_data()
    row = [data["category"], data["name"], data["partner"], message.from_user.id, message.from_user.username or "", message.text.lower(), "ожидает оплату"]
    try:
        sheet.append_row(row)
    except:
        await message.answer("⚠️ Не удалось записать в таблицу.")
    await message.answer("💳 Для завершения регистрации переведите взнос по реквизитам:

"
                         "**Реквизиты:**
Сбербанк: 2202 2023 4567 1234

"
                         "После оплаты отправьте, пожалуйста, чек сюда.")
    await Form.payment.set()

@dp.message_handler(content_types=types.ContentType.PHOTO, state=Form.payment)
async def process_payment(message: types.Message, state: FSMContext):
    await message.answer("Спасибо! 🧾 Чек получен. Мы подтвердим вашу оплату вручную в ближайшее время.")
    await state.finish()

def yes_no_kb():
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add("Да", "Нет")

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
