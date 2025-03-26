import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# === НАСТРОЙКИ ===
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
SPREADSHEET_NAME = 'Друг 2025'

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

CATEGORIES = list(CATEGORY_LIMITS.keys())

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Подключение к Google Sheets
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.prod.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).worksheet("Все заявки")

# Временное хранилище
user_data = {}

def get_registered_count(category):
    records = sheet.get_all_records()
    return sum(1 for r in records if r['Категория'] == category and r['Тип участия'] == 'Основной')

def get_category_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for cat in CATEGORIES:
        markup.add(KeyboardButton(cat))
    return markup

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Добро пожаловать на теннисный турнир ДРУГ 2025!

"
        "Выберите категорию участия:",
        reply_markup=get_category_keyboard()
    )
    user_data[message.chat.id] = {}

@dp.message_handler(lambda msg: msg.text in CATEGORIES)
async def category_handler(msg: types.Message):
    user_data[msg.chat.id]['category'] = msg.text
    await msg.answer("Как вас зовут? (ФИО Игрока 1)", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(lambda msg: 'category' in user_data.get(msg.chat.id, {}) and 'name1' not in user_data[msg.chat.id])
async def name1_handler(msg: types.Message):
    user_data[msg.chat.id]['name1'] = msg.text
    category = user_data[msg.chat.id]['category']
    if "Doubles" in category or "Mixed" in category:
        await msg.answer("Как зовут вашего напарника?")
    else:
        user_data[msg.chat.id]['name2'] = ""
        await msg.answer("Укажите ваш номер телефона:")

@dp.message_handler(lambda msg: 'name1' in user_data.get(msg.chat.id, {}) and 'name2' not in user_data[msg.chat.id] and (
    "Doubles" in user_data[msg.chat.id]['category'] or "Mixed" in user_data[msg.chat.id]['category']
))
async def name2_handler(msg: types.Message):
    user_data[msg.chat.id]['name2'] = msg.text
    await msg.answer("Укажите ваш номер телефона:")

@dp.message_handler(lambda msg: 'name2' in user_data.get(msg.chat.id, {}) and 'phone' not in user_data[msg.chat.id])
async def phone_handler(msg: types.Message):
    user_data[msg.chat.id]['phone'] = msg.text
    await msg.answer("Укажите ваш ник в Telegram (@username):")

@dp.message_handler(lambda msg: 'phone' in user_data.get(msg.chat.id, {}) and 'telegram' not in user_data[msg.chat.id])
async def telegram_handler(msg: types.Message):
    user_data[msg.chat.id]['telegram'] = msg.text
    data = user_data[msg.chat.id]
    category = data['category']
    registered = get_registered_count(category)
    limit = CATEGORY_LIMITS[category]

    slot_type = "Основной" if registered < limit else "Лист ожидания"
    user_data[msg.chat.id]['slot'] = slot_type

    # Запись в таблицу
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [now, category, data['name1'], data.get('name2', ""), data['phone'], data['telegram'], slot_type, "Не оплачено", ""]
    sheet.append_row(row)

    if slot_type == "Основной":
        await msg.answer(
            "Вы зарегистрированы в основную сетку.

"
            "Чтобы завершить регистрацию, переведите 1000₽ по следующим реквизитам:

"
            "💳 *СБП/Тинькофф*: 1234567890123456
"
            "👤 *Получатель*: Иванов И.И.

"
            "После перевода пришлите фото или скриншот чека сюда.",
            parse_mode="Markdown"
        )
    else:
        await msg.answer("Вы добавлены в лист ожидания. Мы сообщим вам, если появится свободное место.")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_payment_photo(msg: types.Message):
    photo_id = msg.photo[-1].file_id
    records = sheet.get_all_records()
    telegram = msg.from_user.username or user_data[msg.chat.id].get('telegram')
    for idx, row in enumerate(records, start=2):
        if row['Telegram'] == telegram and row['Статус оплаты'] == "Не оплачено":
            sheet.update_cell(idx, 8, "Ожидает подтверждения")
            sheet.update_cell(idx, 9, photo_id)
            await msg.answer("Чек получен. Ожидайте подтверждения.")
            return
    await msg.answer("Не удалось найти вашу заявку или чек уже получен.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
