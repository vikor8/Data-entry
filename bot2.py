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
DB_PATH = "/home/viktor/bsg_bot1/Data-entry/workshop_data_1.db"



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

# Функция для получения или создания пользователя
def get_or_create_user(telegram_id, full_name=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT telegram_id, full_name FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        
        if user:
            user_id, existing_full_name = user
            conn.close()
            return user_id, existing_full_name
        elif full_name:
            # Создаем нового пользователя
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO users (telegram_id, full_name)
                VALUES (?, ?)
            ''', (telegram_id, full_name))
            
            cursor.execute('''
                INSERT INTO user_creation_dates (telegram_id, created_at)
                VALUES (?, ?)
            ''', (telegram_id, current_time))
            
            conn.commit()
            conn.close()
            return telegram_id, full_name
        else:
            conn.close()
            return None, None
    except Exception as e:
        logging.error(f"Ошибка в get_or_create_user: {e}")
        if 'conn' in locals():
            conn.close()
        return None, None

# Функция для сохранения данных в базу
def save_qr_data(workshop_name, qr_data, telegram_id):
    try:
        table_name = workshop_name.replace(" ", "_").replace("-", "_")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли уже запись с таким QR-кодом
        cursor.execute(f'SELECT id FROM "{table_name}" WHERE qr_data = ? AND telegram_id = ?', (qr_data, telegram_id))
        existing_record = cursor.fetchone()
        
        if existing_record:
            # Если запись существует, обновляем дату изменения
            cursor.execute(f'''
                UPDATE "{table_name}" 
                SET modification_date = ?
                WHERE qr_data = ? AND telegram_id = ?
            ''', (current_time, qr_data, telegram_id))
            result = "обновлена"
        else:
            # Если записи нет, создаем новую
            cursor.execute(f'''
                INSERT INTO "{table_name}" (qr_data, creation_date, telegram_id) 
                VALUES (?, ?, ?)
            ''', (qr_data, current_time, telegram_id))
            result = "сохранена"
        
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"Ошибка в save_qr_data: {e}")
        if 'conn' in locals():
            conn.close()
        raise e

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Очищаем выбор участка при новом запуске
    context.user_data.pop('selected_workshop', None)
    context.user_data.pop('awaiting_full_name', None)
    
    # Проверяем, есть ли пользователь в базе
    telegram_id = update.effective_user.id
    user_id, full_name = get_or_create_user(telegram_id)
    
    if not user_id:
        # Если пользователя нет, запрашиваем Ф.И.О.
        context.user_data['awaiting_full_name'] = True
        await update.message.reply_text(
            "Добро пожаловать! Пожалуйста, введите ваше Ф.И.О. в формате:\n"
            "Фамилия И.О. (например: Иванов И.И.)"
        )
        return
    
    # Создаем клавиатуру с выбором участков
    keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"Здравствуйте, {full_name}!\n"
        "На каком участке вы работаете?",
        reply_markup=reply_markup
    )

# Обработчик ввода Ф.И.О.
async def handle_full_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get('awaiting_full_name'):
        return False
    
    full_name = update.message.text.strip()
    
    # Проверяем формат Ф.И.О.
    if not full_name or len(full_name.split()) < 2:
        await update.message.reply_text(
            "Пожалуйста, введите Ф.И.О. в правильном формате:\n"
            "Фамилия И.О. (например: Иванов И.И.)"
        )
        return True
    
    telegram_id = update.effective_user.id
    
    # Создаем пользователя
    try:
        user_id, saved_full_name = get_or_create_user(telegram_id, full_name)
        
        if user_id:
            context.user_data.pop('awaiting_full_name', None)
            
            # Создаем клавиатуру с выбором участков
            keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                f"Спасибо, {saved_full_name}! Теперь вы зарегистрированы в системе.\n"
                "На каком участке вы работаете?",
                reply_markup=reply_markup
            )
            return True
        else:
            await update.message.reply_text("Произошла ошибка при регистрации. Попробуйте еще раз.")
            return True
    except Exception as e:
        logging.error(f"Ошибка при создании пользователя: {e}")
        await update.message.reply_text("Произошла ошибка при регистрации. Попробуйте еще раз.")
        return True

# Обработчик выбора участка
async def handle_workshop_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, если ожидается ввод Ф.И.О.
    if context.user_data.get('awaiting_full_name'):
        handled = await handle_full_name_input(update, context)
        if handled:
            return
    
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
            telegram_id = update.effective_user.id
            user_id, full_name = get_or_create_user(telegram_id)
            
            if not user_id:
                context.user_data['awaiting_full_name'] = True
                await update.message.reply_text(
                    "Пожалуйста, введите ваше Ф.И.О. в формате:\n"
                    "Фамилия И.О. (например: Иванов И.И.)"
                )
                return
            
            keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                f"Здравствуйте, {full_name}!\n"
                "Сначала выберите участок из списка.",
                reply_markup=reply_markup
            )

# Обработчик QR-кода или текста
async def handle_qr_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, если ожидается ввод Ф.И.О.
    if context.user_data.get('awaiting_full_name'):
        await handle_full_name_input(update, context)
        return
    
    # Проверяем, выбран ли участок
    selected_workshop = context.user_data.get('selected_workshop')
    
    if not selected_workshop:
        # Если участок не выбран, предлагаем выбрать через /start
        telegram_id = update.effective_user.id
        user_id, full_name = get_or_create_user(telegram_id)
        
        if not user_id:
            context.user_data['awaiting_full_name'] = True
            await update.message.reply_text(
                "Пожалуйста, введите ваше Ф.И.О. в формате:\n"
                "Фамилия И.О. (например: Иванов И.И.)"
            )
            return
        
        keyboard = [[KeyboardButton(workshop)] for workshop in WORKSHOPS]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            f"Здравствуйте, {full_name}!\n"
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
    
    # Получаем ID пользователя
    telegram_id = update.effective_user.id
    try:
        user_id, full_name = get_or_create_user(telegram_id)
        
        if not user_id:
            context.user_data['awaiting_full_name'] = True
            await update.message.reply_text(
                "Пожалуйста, введите ваше Ф.И.О. в формате:\n"
                "Фамилия И.О. (например: Иванов И.И.)"
            )
            return
        
        # Сохраняем данные в базу
        result = save_qr_data(selected_workshop, qr_data, telegram_id)
        await update.message.reply_text(
            f"Данные {result} для участка: {selected_workshop}\n"
            f"QR-данные: {qr_data}\n"
            f"Пользователь: {full_name}"
        )
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении данных. Попробуйте еще раз.")

# Основная функция
def main() -> None:
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
