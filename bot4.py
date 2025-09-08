import logging
import sqlite3
from datetime import datetime
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image
from pyzbar import pyzbar
import re

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (ваш)
TOKEN = "8276595091:AAFQ9svHr5Upeo27cTRXKjxEdMvUmRwQ41E"

# Полный путь к базе данных
DB_PATH = "/home/viktor/freedom/workshop_data_1.db"

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
    "Участок упаковки",
    "Аутсорсинг"  # ✅ Новый участок добавлен
]

def validate_qr_data(qr_data):
    """
    Проверяет данные QR-кода на соответствие требованиям:
    - Только цифры, латинские буквы и знаки / . _ -
    - Каждый знак / . _ - можно использовать только 1 раз
    """
    if not qr_data:
        return False, "Данные не могут быть пустыми"
    
    # Проверяем, что данные содержат только разрешенные символы
    allowed_pattern = r'^[a-zA-Z0-9/._\-]+$'
    if not re.match(allowed_pattern, qr_data):
        return False, "Данные могут содержать только цифры, латинские буквы и знаки / . _ -"
    
    # Проверяем, что каждый специальный знак встречается не более 1 раза
    special_chars = ['/', '.', '_', '-']
    for char in special_chars:
        if qr_data.count(char) > 1:
            return False, f"Знак '{char}' можно использовать только один раз"
    
    return True, "OK"

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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if workshop_name == "Аутсорсинг":
            # Работаем с таблицей "аутсорсинг"
            cursor.execute('PRAGMA foreign_keys = ON;')

            # Проверяем, существует ли уже запись с таким артикулом
            cursor.execute('SELECT "дата_заявки", "дата_получения" FROM "аутсорсинг" WHERE "артикул" = ?', (qr_data,))
            existing = cursor.fetchone()

            if existing is None:
                # Первый ввод — записываем дату заявки
                cursor.execute('''
                    INSERT INTO "аутсорсинг" ("артикул", "дата_заявки", "аутсорсер")
                    VALUES (?, ?, ?)
                ''', (qr_data, current_time, telegram_id))
                result = "артикул отправлен в аутсорсинг"
            elif existing[1] is None:
                # Уже есть дата заявки, но нет даты получения — обновляем
                cursor.execute('''
                    UPDATE "аутсорсинг"
                    SET "дата_получения" = ?
                    WHERE "артикул" = ?
                ''', (current_time, qr_data))
                result = "артикул получен из аутсорсинга"
            else:
                # Оба поля уже заполнены — повторный ввод
                result = "артикул уже был получен ранее"
        else:
            # Логика для обычных участков (с таблицами по имени участка)
            table_name = workshop_name.replace(" ", "_").replace("-", "_")
            
            # Проверяем существование записи
            cursor.execute(f'SELECT id FROM "{table_name}" WHERE qr_data = ? AND telegram_id = ?', (qr_data, telegram_id))
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Обновляем дату изменения
                cursor.execute(f'''
                    UPDATE "{table_name}" 
                    SET modification_date = ?
                    WHERE qr_data = ? AND telegram_id = ?
                ''', (current_time, qr_data, telegram_id))
                result = "обновлены"
            else:
                # Создаём новую запись
                cursor.execute(f'''
                    INSERT INTO "{table_name}" (qr_data, creation_date, telegram_id) 
                    VALUES (?, ?, ?)
                ''', (qr_data, current_time, telegram_id))
                result = "сохранены"
        
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
    # Очищаем состояние
    context.user_data.pop('selected_workshop', None)
    context.user_data.pop('awaiting_full_name', None)
    
    telegram_id = update.effective_user.id
    user_id, full_name = get_or_create_user(telegram_id)
    
    if not user_id:
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
        context.user_data['selected_workshop'] = selected_workshop
        
        # Убираем клавиатуру выбора участков
        reply_markup = ReplyKeyboardMarkup([[]], resize_keyboard=True)
        
        await update.message.reply_text(
            f"Вы выбрали: {selected_workshop}\n"
            "Теперь отправьте артикул изделия или QR-код (текст или фото) для сохранения.\n"
            "Для выбора другого участка отправьте /start.",
            reply_markup=reply_markup
        )
    else:
        # Если сообщение не является выбором участка
        selected_workshop = context.user_data.get('selected_workshop')
        if selected_workshop:
            await handle_qr_data(update, context)
        else:
            # Напоминаем выбрать участок
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
    if context.user_data.get('awaiting_full_name'):
        await handle_full_name_input(update, context)
        return
    
    selected_workshop = context.user_data.get('selected_workshop')
    if not selected_workshop:
        # Напоминаем выбрать участок
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
        qr_data = update.message.text.strip()
        if not qr_data:
            await update.message.reply_text("Пожалуйста, отправьте непустые данные.")
            return
        is_valid, error_message = validate_qr_data(qr_data)
        if not is_valid:
            await update.message.reply_text(f"❌ Ошибка ввода данных:\n{error_message}")
            return
    elif update.message.photo:
        await update.message.reply_text("Обрабатываю фото, подождите...")
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(BytesIO(bytes(photo_bytes)))
        decoded_objects = pyzbar.decode(image)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode("utf-8")
            is_valid, error_message = validate_qr_data(qr_data)
            if not is_valid:
                await update.message.reply_text(
                    f"❌ Ошибка в данных QR-кода:\n{error_message}\n"
                    "Пожалуйста, отправьте другой QR-код или введите данные вручную."
                )
                return
        else:
            await update.message.reply_text(
                "QR-код на фото не найден или не распознан.\n"
                "Пожалуйста, отправьте четкое фото QR-кода или введите данные вручную."
            )
            return
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте текст или фото QR-кода."
        )
        return

    # Сохраняем данные
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

        result = save_qr_data(selected_workshop, qr_data, telegram_id)
        await update.message.reply_text(
            f"✅ {result.capitalize()} для участка: {selected_workshop}\n"
            f"Артикул: {qr_data}\n"
            f"Пользователь: {full_name}"
        )
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении данных. Попробуйте еще раз.")

# Основная функция
def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workshop_selection))
    application.add_handler(MessageHandler(filters.PHOTO, handle_qr_data))
    
    application.run_polling()

if __name__ == '__main__':
    main()
