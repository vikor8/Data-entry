#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BSG Аналитик - Telegram бот для анализа данных из базы данных workshop_data_1.db.
Исправлены ошибки с пустыми датами и улучшен вывод.
"""

import logging
import re
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Импортируем функции из модуля базы данных
# Убедитесь, что DB_PATH импортирован
from database import (
    search_by_order,
    search_by_item,
    search_packaged_items,
    search_items_by_type_and_status, # Новая функция
    is_user_registered,
    register_user,
    get_user_full_name,
    get_table_names,
    get_last_workshop_for_item,
    strip_suffix,
    DB_PATH # Импортируем путь к БД
)

# === ИМПОРТ ИЗ DEVELOPMENT ===
from development import get_future_orders

# === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === ТОКЕН БОТА ===
TOKEN = "8414355250:AAGyGpcYMIGgeR6hKAF35niRT0HE06zyke4"

# === СОСТОЯНИЯ ===
WAITING_FOR_FULL_NAME = 1
WAITING_FOR_PACKAGING_ORDER = 2
WAITING_FOR_ZAKLADKI_ORDER = 3
WAITING_FOR_REKLAMACIA_ORDER = 4

# === ФОРМАТИРОВАНИЕ ТАБЛИЦЫ ===
def format_table_data(data, headers):
    """Форматирует данные в виде таблицы с моноширинным шрифтом."""
    if not data:
        return ""
    col_widths = [len(str(h)) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    format_str = " │ ".join([f"{{:<{w}}}" for w in col_widths])
    lines = [format_str.format(*headers)]
    lines.append("─┼─".join(["─" * w for w in col_widths]))
    for row in data:
        lines.append(format_str.format(*[str(cell) for cell in row]))
    return "```\n" + "\n".join(lines) + "\n```"

# === ОБРАБОТЧИК /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username or "Пользователь"

    if is_user_registered(telegram_id):
        full_name = get_user_full_name(telegram_id)
        welcome_text = (
            f"🤖 *BSG Аналитик*, {full_name}!\n\n"
            "🔍 Я предоставляю информацию о заказах и изделиях.\n\n"
            "📤 *Как пользоваться:*\n"
            "• Введите *номер заказа* (например, `164`)\n"
            "• Введите *номер изделия* (например, `164.21`)\n"
            "• Используйте кнопки *'Упаковка'*, *'Закладные'*, *'Рекламация'*, *'КБ'*\n"
            "• Используйте /help для справки\n"
        )
        keyboard = [
            [KeyboardButton("Упаковка"), KeyboardButton("Закладные")],
            [KeyboardButton("Рекламация"), KeyboardButton("КБ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        context.user_data['telegram_id'] = telegram_id
        registration_text = (
            f"👋 Привет, {user_name}!\n\n"
            "Для работы с ботом необходима регистрация.\n"
            "Пожалуйста, введите ваше *Ф.И.О.* в формате:\n"
            "`Иванов Иван Иванович` или `Иванов И.И.`"
        )
        await update.message.reply_text(registration_text, parse_mode='Markdown')
        return WAITING_FOR_FULL_NAME

# === ОБРАБОТЧИК РЕГИСТРАЦИИ ===
async def handle_full_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text.strip()
    if not full_name or len(full_name.split()) < 2:
        await update.message.reply_text(
            "❌ Неверный формат Ф.И.О.\n\n"
            "Пожалуйста, введите `Фамилия Имя Отчество` или `Фамилия И.И.`"
        )
        return WAITING_FOR_FULL_NAME

    telegram_id = context.user_data.get('telegram_id')
    if not telegram_id:
        await update.message.reply_text("❌ Ошибка регистрации. Начните с /start")
        return ConversationHandler.END

    if register_user(telegram_id, full_name):
        success_text = (
            f"✅ *Регистрация завершена!*\n\n"
            f"Добро пожаловать, {full_name}!\n\n"
            "🔍 Теперь вы можете использовать все функции бота."
        )
        keyboard = [
            [KeyboardButton("Упаковка"), KeyboardButton("Закладные")],
            [KeyboardButton("Рекламация"), KeyboardButton("КБ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ошибка при регистрации.")
        return ConversationHandler.END

# === ОБРАБОТЧИК КНОПКИ КБ ===
async def kb_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return

    orders = get_future_orders()
    if not orders:
        await update.message.reply_text("📋 *Будущих заказов нет.*", parse_mode='Markdown')
        return

    headers = ["№заказа", "Заказчик", "Город", "Дата отгрузки"]
    table_str = format_table_data(orders, headers)
    response = f"📋 *Будущие заказы из КБ*:\n\n{table_str}"

    # --- ОБРЕЗАНИЕ СООБЩЕНИЯ ---
    if len(response) > 4096:
        truncated = response[:4000]
        for char in ['*', '_', '`']:
            if truncated.count(char) % 2 != 0:
                last = truncated.rfind(char)
                if last != -1:
                    truncated = truncated[:last]
        response = truncated + "\n\n⚠️ *Часть данных скрыта*"

    await update.message.reply_text(response, parse_mode='Markdown')

# === ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return

    user_input = update.message.text.strip()

    if user_input == "Упаковка":
        await packaging_button_handler(update, context)
        return
    elif user_input == "Закладные":
        await zakladki_button_handler(update, context)
        return
    elif user_input == "Рекламация":
        await reklamacia_button_handler(update, context)
        return
    elif user_input == "КБ":
        await kb_button_handler(update, context)
        return

    if not re.match(r'^[\d./_zZrR]+$', user_input):
        await update.message.reply_text("❗ Введите номер заказа или изделия.")
        return

    # === ПОИСК ПО ИЗДЕЛИЮ ===
    if '.' in user_input and re.search(r'\.(\d+)', user_input):
        item_results = search_by_item(user_input)
        if not item_results:
            await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
            return

        headers = ["Участок", "ФИО", "Запущено", "Изменено"]
        table_data = []
        for result in item_results:
            workshop = result[0]
            # qr_data = result[1] # Не используется в выводе
            telegram_id_user = result[2]
            creation_date = result[3]
            modification_date = result[4]

            fio = get_user_full_name(telegram_id_user)
            created = creation_date if creation_date else "-"
            modified = modification_date if modification_date else "-"

            table_data.append([workshop, fio, created, modified])

        table_str = format_table_data(table_data, headers)
        response = f"🔧 *Информация об изделии {user_input}:*\n\n{table_str}"

    # === ПОИСК ПО ЗАКАЗУ (УПРОЩЁННЫЙ ВЫВОД) ===
    else:
        base_order, _ = strip_suffix(user_input)
        if not base_order:
            await update.message.reply_text("❗ Неверный номер заказа.")
            return

        # Получаем упакованные
        packaged_items = {item[0] for item in search_packaged_items(base_order)}

        # Все изделия заказа
        all_items = set()
        conn = sqlite3.connect(DB_PATH) # Используем константу из database.py
        cursor = conn.cursor()
        pattern = f"{base_order}%"
        tables = get_table_names()

        for table in tables:
            if table == "аутсорсинг":
                continue
            try:
                cursor.execute(f'SELECT qr_data FROM "{table}" WHERE qr_data LIKE ?', (pattern,))
                all_items.update(row[0] for row in cursor.fetchall())
            except sqlite3.Error as e:
                 logger.error(f"Ошибка при поиске всех изделий в таблице {table}: {e}")
        conn.close()

        items_in_work = [i for i in all_items if i not in packaged_items]
        packed_items_list = [i for i in all_items if i in packaged_items]

        response = f"📋 *Сводка по заказу {base_order}*\n\n"

        # --- Таблица 1: Изделия в работе ---
        if items_in_work:
            headers = ["Артикул", "Участок", "ФИО", "Дата"]
            table_data = []
            for item in sorted(items_in_work):
                info = get_last_workshop_for_item(item)
                if info:
                    workshop, fio, date = info
                else:
                    workshop, fio, date = "Неизвестно", "-", "-"
                table_data.append([item, workshop, fio, date])
            table_str = format_table_data(table_data, headers)
            response += f"🔧 *Изделия в работе*:\n{table_str}\n"
        else:
            response += "🔧 *Изделия в работе*: _нет_\n\n"

        # --- Таблица 2: Упакованные изделия ---
        if packed_items_list:
            headers = ["Артикул", "Участок", "ФИО", "Дата"]
            table_data = []
            
            # Получаем детали упакованных изделий
            packaged_details = search_packaged_items(base_order)
            # Создаем словарь для быстрого поиска
            packaged_dict = {detail[0]: detail for detail in packaged_details}

            # Формируем таблицу
            for item in sorted(packed_items_list):
                detail = packaged_dict.get(item)
                if detail:
                    qr_data, fio, created, modified = detail
                    # Проверка на аутсорсинг (по наличию в таблице аутсорсинг)
                    conn = sqlite3.connect(DB_PATH) # Используем константу из database.py
                    cursor = conn.cursor()
                    cursor.execute('SELECT "артикул" FROM "аутсорсинг" WHERE "артикул" = ?', (qr_data,))
                    is_outsourcing = cursor.fetchone() is not None
                    conn.close()
                    
                    if is_outsourcing:
                        workshop = "Упаковка (аутсорсинг)"
                        date = modified if modified else (created if created else "-") # Дата получения
                    else:
                        workshop = "Упаковка"
                        date = created if created else "-" # Дата запуска
                    table_data.append([item, workshop, fio, date])
                else:
                     table_data.append([item, "Упаковка", "-", "-"])
            table_str = format_table_data(table_data, headers)
            response += f"📦 *Упакованные изделия*:\n{table_str}\n"
        else:
            response += "📦 *Упакованные изделия*: _нет_\n"

    # --- ОБРЕЗАНИЕ СООБЩЕНИЯ ---
    if len(response) > 4096:
        truncated = response[:4000]
        for char in ['*', '_', '`']:
            if truncated.count(char) % 2 != 0:
                last = truncated.rfind(char)
                if last != -1:
                    truncated = truncated[:last]
        response = truncated + "\n\n⚠️ *Часть данных скрыта*"

    await update.message.reply_text(response, parse_mode='Markdown')

# === ОБРАБОТЧИКИ КНОПОК ===

async def packaging_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопки 'Упаковка'"""
    await update.message.reply_text("📦 Введите номер заказа (например, `164`):", parse_mode='Markdown')
    return WAITING_FOR_PACKAGING_ORDER

async def zakladki_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопки 'Закладные'"""
    await update.message.reply_text("🔖 Введите номер заказа (например, `164`):", parse_mode='Markdown')
    return WAITING_FOR_ZAKLADKI_ORDER

async def reklamacia_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопки 'Рекламация'"""
    await update.message.reply_text("⚠️ Введите номер заказа (например, `164`):", parse_mode='Markdown')
    return WAITING_FOR_REKLAMACIA_ORDER

# === ОБРАБОТЧИКИ ВВОДА ЗАКАЗА ПОСЛЕ НАЖАТИЯ КНОПОК ===

async def handle_packaging_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода номера заказа после нажатия кнопки 'Упаковка'"""
    return await _handle_specific_order_input(update, context, order_type="packaging")

async def handle_zakladki_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода номера заказа после нажатия кнопки 'Закладные'"""
    return await _handle_specific_order_input(update, context, order_type="zakladki")

async def handle_reklamacia_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода номера заказа после нажатия кнопки 'Рекламация'"""
    return await _handle_specific_order_input(update, context, order_type="reklamacia")

# --- Вспомогательная функция для обработки ---
async def _handle_specific_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE, order_type: str) -> int:
    """Вспомогательная функция для обработки ввода заказа по типу"""
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return ConversationHandler.END

    user_input = update.message.text.strip()

    if not re.match(r'^[\d./_]+$', user_input): # Убраны zZrR для кнопок
        message_map = {
            "packaging": "📦 Введите корректный номер заказа (например, `164`):",
            "zakladki": "🔖 Введите корректный номер заказа (например, `164`):",
            "reklamacia": "⚠️ Введите корректный номер заказа (например, `164`):",
        }
        await update.message.reply_text(message_map.get(order_type, "❗ Введите номер заказа."), parse_mode='Markdown')
        state_map = {
            "packaging": WAITING_FOR_PACKAGING_ORDER,
            "zakladki": WAITING_FOR_ZAKLADKI_ORDER,
            "reklamacia": WAITING_FOR_REKLAMACIA_ORDER,
        }
        return state_map.get(order_type, ConversationHandler.END)

    base_order, _ = strip_suffix(user_input)
    if not base_order:
        await update.message.reply_text("❗ Неверный номер заказа.")
        state_map = {
            "packaging": WAITING_FOR_PACKAGING_ORDER,
            "zakladki": WAITING_FOR_ZAKLADKI_ORDER,
            "reklamacia": WAITING_FOR_REKLAMACIA_ORDER,
        }
        return state_map.get(order_type, ConversationHandler.END)

    # Логика по типу кнопки
    if order_type == "packaging":
        # Логика для упаковки (уже реализована вами)
        # Показываем упакованные изделия
        packaged_items_result = search_packaged_items(base_order)
        packaged_items_set = {item[0] for item in packaged_items_result}

        if not packaged_items_set:
            response = f"📦 *Упакованные изделия по заказу {base_order}*: _нет_"
        else:
            headers = ["Артикул", "Участок", "ФИО", "Дата"]
            table_data = []
            # Используем уже полученные данные из search_packaged_items
            packaged_dict = {detail[0]: detail for detail in packaged_items_result}
            
            for item in sorted(packaged_items_set):
                detail = packaged_dict.get(item)
                if detail:
                    qr_data, fio, created, modified = detail
                    # Проверка на аутсорсинг (по наличию в таблице аутсорсинг)
                    conn = sqlite3.connect(DB_PATH) # Используем константу из database.py
                    cursor = conn.cursor()
                    cursor.execute('SELECT "артикул" FROM "аутсорсинг" WHERE "артикул" = ?', (qr_data,))
                    is_outsourcing = cursor.fetchone() is not None
                    conn.close()
                    
                    if is_outsourcing:
                        workshop = "Упаковка (аутсорсинг)"
                        date = modified if modified else (created if created else "-") # Дата получения
                    else:
                        workshop = "Упаковка"
                        date = created if created else "-" # Дата запуска
                    table_data.append([item, workshop, fio, date])
                else:
                     table_data.append([item, "Упаковка", "-", "-"])
            
            table_str = format_table_data(table_data, headers)
            response = f"📦 *Упакованные изделия по заказу {base_order}*:\n{table_str}"

        # --- ОБРЕЗАНИЕ СООБЩЕНИЯ ---
        if len(response) > 4096:
            truncated = response[:4000]
            for char in ['*', '_', '`']:
                if truncated.count(char) % 2 != 0:
                    last = truncated.rfind(char)
                    if last != -1:
                        truncated = truncated[:last]
            response = truncated + "\n\n⚠️ *Часть данных скрыта*"

        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END

    elif order_type == "zakladki":
        # Логика для закладных
        item_type_id = 2 # 2 = закладная

        # Получаем все изделия этого типа по заказу
        all_items = search_items_by_type_and_status(base_order, item_type_id, is_packed=False)  # Не упакованные
        packed_items = search_items_by_type_and_status(base_order, item_type_id, is_packed=True)  # Упакованные

        # Формируем ответ
        response = f"📋 *Закладные заказа {base_order}*:\n\n"

        # Таблица 1: Активные (Не упакованы)
        if all_items:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = []
            for qr_data, workshop, fio, created in all_items:
                table_data.append([qr_data, workshop, fio, created])
            table_str = format_table_data(table_data, headers)
            response += f"🔴 *Активные (Не упакованы)*:\n{table_str}\n\n"
        else:
            response += f"🔴 *Активные (Не упакованы)*: _нет_\n\n"

        # Таблица 2: Уже упакованы
        if packed_items:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = []
            for qr_data, workshop, fio, created in packed_items:
                table_data.append([qr_data, workshop, fio, created])
            table_str = format_table_data(table_data, headers)
            response += f"📦 *Уже упакованы*:\n{table_str}\n"
        else:
            response += f"📦 *Уже упакованы*: _нет_\n"

        # --- ОБРЕЗАНИЕ СООБЩЕНИЯ ---
        if len(response) > 4096:
            truncated = response[:4000]
            for char in ['*', '_', '`']:
                if truncated.count(char) % 2 != 0:
                    last = truncated.rfind(char)
                    if last != -1:
                        truncated = truncated[:last]
            response = truncated + "\n\n⚠️ *Часть данных скрыта*"

        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END

    elif order_type == "reklamacia":
        # Логика для рекламаций
        item_type_id = 3 # 3 = рекламация

        # Получаем все изделия этого типа по заказу
        all_items = search_items_by_type_and_status(base_order, item_type_id, is_packed=False)  # Не упакованные
        packed_items = search_items_by_type_and_status(base_order, item_type_id, is_packed=True)  # Упакованные

        # Формируем ответ
        response = f"📋 *Рекламации заказа {base_order}*:\n\n"

        # Таблица 1: Активные (Не упакованы)
        if all_items:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = []
            for qr_data, workshop, fio, created in all_items:
                table_data.append([qr_data, workshop, fio, created])
            table_str = format_table_data(table_data, headers)
            response += f"🔴 *Активные (Не упакованы)*:\n{table_str}\n\n"
        else:
            response += f"🔴 *Активные (Не упакованы)*: _нет_\n\n"

        # Таблица 2: Уже упакованы
        if packed_items:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = []
            for qr_data, workshop, fio, created in packed_items:
                table_data.append([qr_data, workshop, fio, created])
            table_str = format_table_data(table_data, headers)
            response += f"📦 *Уже упакованы*:\n{table_str}\n"
        else:
            response += f"📦 *Уже упакованы*: _нет_\n"

        # --- ОБРЕЗАНИЕ СООБЩЕНИЯ ---
        if len(response) > 4096:
            truncated = response[:4000]
            for char in ['*', '_', '`']:
                if truncated.count(char) % 2 != 0:
                    last = truncated.rfind(char)
                    if last != -1:
                        truncated = truncated[:last]
            response = truncated + "\n\n⚠️ *Часть данных скрыта*"

        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END

    return ConversationHandler.END

# === СПРАВКА ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return

    help_text = (
        "📖 *Справка BSG Аналитик*\n\n"
        "🔍 *Поиск по заказу:* `164`\n"
        "🔍 *Поиск по изделию:* `164.21`\n"
        "📦 *Упаковка:* нажмите и введите заказ\n"
        "🔖 *Закладные:* нажмите и введите заказ\n"
        "⚠️ *Рекламация:* нажмите и введите заказ\n"
        "📋 *КБ:* нажмите, чтобы посмотреть будущие заказы\n\n"
        "💡 *Примечание:* Закладные и рекламации не показываются, если изделие уже упаковано."
    )
    keyboard = [
        [KeyboardButton("Упаковка"), KeyboardButton("Закладные")],
        [KeyboardButton("Рекламация"), KeyboardButton("КБ")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Регистрация (обновляем states)
    registration_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # Добавляем кнопки как entry points тоже, чтобы можно было начать с них
            MessageHandler(filters.Regex("^Упаковка$"), packaging_button_handler),
            MessageHandler(filters.Regex("^Закладные$"), zakladki_button_handler),
            MessageHandler(filters.Regex("^Рекламация$"), reklamacia_button_handler),
            MessageHandler(filters.Regex("^КБ$"), kb_button_handler),  # <-- НОВОЕ
        ],
        states={
            WAITING_FOR_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name_input)],
            WAITING_FOR_PACKAGING_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_packaging_order_input)],
            WAITING_FOR_ZAKLADKI_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_zakladki_order_input)],
            WAITING_FOR_REKLAMACIA_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reklamacia_order_input)],
        },
        fallbacks=[],
        allow_reentry=True # Позволяет перезапускать разговор
    )

    # Добавляем обработчики
    application.add_handler(registration_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == '__main__':
    main()
