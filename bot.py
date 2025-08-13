import logging
import sqlite3
from datetime import datetime
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image
from pyzbar import pyzbar
import os

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (ваш)
TOKEN = "8276595091:AAFQ9svHr5Upeo27cTRXKjxEdMvUmRwQ41E"

# Полный путь к базе данных
DB_PATH = "/srv/dev-disk-by-uuid-6cbacaea-af88-4ced-8990-f4f163606aae/home/bot/workshop_data.db"

# Создаем директорию, если она не существует
db_dir = os.path.dirname(DB_PATH)
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

# Список участков (добавлен новый участок)
WORKSHOPS = [
    "Участок раскроя",
    "Участок кормления",
    "Участок пресса",
    "Участок ЧПУ",
    "Участок рекламы",
    "Участок сборки",
    "Участок покраски",
    "Участок металла",
    "Участок порошковой покраски",
    "Участок стекла",
    "Участок упаковки"  # Новый участок
]

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Создаем таблицу для каждого участка
    for workshop in WORKSHOPS:
        table_name = workshop.replace(" ", "_").replace("-", "_")
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qr_data TEXT NOT NULL,
                creation_date TEXT NOT NULL,
                modification_date TEXT
            )
        ''')
    
    conn.commit()
    conn.close()

# Функция для сохранения данных в базу
def save_qr_data(workshop_name, qr_data):
    table_name = workshop_name.replace(" ", "_").replace("-", "_")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем, существует ли уже запись с таким QR-кодом
    cursor.execute(f'SELECT id FROM "{table_name}" WHERE qr_data = ?', (qr_data,))
    existing_record = cursor.fetchone()
    
    if existing_record:
        # Если запись существует, обновляем дату изменения
        cursor.execute(f'''
            UPDATE "{table_name}" 
            SET modification_date = ? 
            WHERE qr_data = ?
        ''', (current_time, qr_data))
        result = "обновлена"
    else:
        # Если записи нет, создаем новую
        cursor.execute(f'''
            INSERT INTO "{table_name}" (qr_data, creation_date) 
            VALUES (?, ?)
        ''', (qr_data, current_time))
        result = "сохранена"
    
    conn.commit()
    conn.close()
    return result

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Очищаем выбор участка при новом запуске
    context.user_data.pop('selected_workshop', None)
    
    # Создаем клавиатуру с выбором участков
    keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "На каком участке вы работаете?",
        reply_markup=reply_markup
    )

# Обработчик выбора участка
async def handle_workshop_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    
    # Проверяем, является ли сообщение выбором участка
    if user_message in WORKSHOPS:
        selected_workshop = user_message
        # Сохраняем выбранный участок в контексте пользователя
        context.user_data['selected_workshop'] = selected_workshop
        
        # Создаем клавиатуру без кнопок (обычная клавиатура)
        reply_markup = ReplyKeyboardMarkup([[]], resize_keyboard=True)
        
        await update.message.reply_text(
            f"Вы выбрали: {selected_workshop}\n"
            "Теперь отправьте данные QR-кода (текст или фото) для сохранения.\n"
            "Для выбора другого участка отправьте /start.",
            reply_markup=reply_markup  # Убираем клавиатуру выбора участков
        )
    else:
        # Если сообщение не является выбором участка
        # Проверяем, выбран ли уже участок
        selected_workshop = context.user_data.get('selected_workshop')
        if selected_workshop:
            # Если участок выбран, обрабатываем как данные QR-кода
            await handle_qr_data(update, context)
        else:
            # Если участок не выбран, напоминаем о необходимости выбора
            keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                "Сначала выберите участок из списка.",
                reply_markup=reply_markup
            )

# Обработчик QR-кода или текста
async def handle_qr_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, выбран ли участок
    selected_workshop = context.user_data.get('selected_workshop')
    
    if not selected_workshop:
        # Если участок не выбран, предлагаем выбрать через /start
        keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Сначала выберите участок. Отправьте /start для выбора.",
            reply_markup=reply_markup
        )
        return
    
    qr_data = ""

    if update.message.text:
        # Обработка текста
        qr_data = update.message.text.strip()
        if not qr_data:
            await update.message.reply_text("Пожалуйста, отправьте непустые текстовые данные.")
            return
    elif update.message.photo:
        # Обработка фото - попытка распознать QR-код
        await update.message.reply_text("Обрабатываю фото, подождите...")
        
        # Получаем фото наилучшего качества (последний элемент в списке)
        photo_file = await update.message.photo[-1].get_file()
        
        # Скачиваем фото в память
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Открываем изображение с помощью PIL
        image = Image.open(BytesIO(bytes(photo_bytes)))
        
        # Пытаемся распознать QR-коды
        decoded_objects = pyzbar.decode(image)
        
        if decoded_objects:
            # Берем данные из первого найденного QR-кода
            qr_data = decoded_objects[0].data.decode("utf-8")
        else:
            await update.message.reply_text(
                "QR-код на фото не найден или не распознан.\n"
                "Пожалуйста, отправьте четкое фото QR-кода или введите данные вручную."
            )
            return
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте текстовые данные QR-кода или фото QR-кода.\n"
            "Для выбора другого участка отправьте /start."
        )
        return
    
    # Сохраняем данные в базу
    try:
        result = save_qr_data(selected_workshop, qr_data)
        await update.message.reply_text(
            f"Данные {result} для участка: {selected_workshop}\n"
            f"QR-данные: {qr_data}"
        )
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении данных.")

# Основная функция
def main() -> None:
    # Инициализация базы данных
    init_db()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    # Обработчик текста для выбора участка и QR-данных
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workshop_selection))
    # Обработчик фото для QR-кодов
    application.add_handler(MessageHandler(filters.PHOTO, handle_qr_data))
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
