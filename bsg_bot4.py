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
from database import (
    search_by_order,
    search_by_item,
    search_packaged_items,
    is_user_registered,
    register_user,
    get_user_full_name,
    get_table_names,
    get_last_workshop_for_item,
    strip_suffix
)

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
            "• Используйте кнопки *'Упаковка'*, *'Закладные'*, *'Рекламация'*\n"
            "• Используйте /help для справки\n"
        )
        keyboard = [[KeyboardButton("Упаковка"), KeyboardButton("Закладные")], [KeyboardButton("Рекламация")]]
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
        keyboard = [[KeyboardButton("Упаковка"), KeyboardButton("Закладные")], [KeyboardButton("Рекламация")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ошибка при регистрации.")
        return ConversationHandler.END

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
        conn = sqlite3.connect("/home/viktor/freedom/workshop_data_1.db")
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
                    # detail[0] = qr_data, detail[1] = fio, detail[2] = creation_date, detail[3] = modification_date
                    qr_data, fio, created, modified = detail
                    # Определяем участок и дату
                    if qr_data in [row[0] for row in search_packaged_items(base_order) if 'аутсорсинг' in str(type(row)) or 'аутсорсинг' in str(row)]:
                        # Это условие не сработает, так как search_packaged_items возвращает общий список
                        # Лучше проверить по qr_data в таблице аутсорсинг
                        # Но мы уже знаем, что это из search_packaged_items, где аутсорсинг идет отдельно
                        # Проще: если qr_data начинается с буквы или содержит буквы - аутсорсинг?
                        # Нет, это артикул. Лучше ориентироваться на структуру search_packaged_items
                        # В search_packaged_items аутсорсинг добавляется отдельно, значит qr_data это артикул
                        # А в Участок_упаковки qr_data это qr_data
                        # Нужно различать, откуда пришел detail
                        # Мы можем добавить признак в search_packaged_items, но проще проверить по qr_data в БД
                        # Но это лишний запрос.
                        # Пока оставим как есть, так как search_packaged_items уже правильно формирует список
                        # и различает Упаковку и Аутсорсинг.
                        # Но в текущем коде они оба попадают в один список.
                        # Переделаем логику search_packaged_items чуть выше.
                        # Сейчас в search_packaged_items:
                        # для Упаковки: (qr_data, fio, created, modified)
                        # для Аутсорсинга: (артикул, fio, дата_заявки, дата_получения)
                        # Значит, если detail[3] (последний элемент) похож на дату получения (не None) - это аутсорсинг
                        # Иначе - упаковка.
                        # Но это не надежно.
                        # Лучше в search_packaged_items добавить тип.
                        # Но для простоты, проверим, есть ли этот qr_data в таблице аутсорсинг
                        conn = sqlite3.connect("/home/viktor/freedom/workshop_data_1.db")
                        cursor = conn.cursor()
                        cursor.execute('SELECT "артикул" FROM "аутсорсинг" WHERE "артикул" = ?', (qr_data,))
                        is_outsourcing = cursor.fetchone() is not None
                        conn.close()
                        
                        if is_outsourcing:
                            workshop = "Упаковка (аутсорсинг)"
                            # Дата получения
                            date = modified if modified else "-"
                        else:
                            workshop = "Упаковка"
                            # Дата запуска (creation_date)
                            date = created if created else "-"
                    else:
                        # Это условие не сработает, так как все элементы из search_packaged_items
                        # Мы должны различать их внутри search_packaged_items
                        # Переделаем search_packaged_items, чтобы она возвращала тип
                        # Но проще добавить признак в результат
                        # Например, добавить "Упаковка" или "Аутсорсинг" в начало кортежа
                        # Внесем изменения в database.py
                        # А пока сделаем так:
                        # Предположим, что если это артикул (а не qr_data), то это аутсорсинг
                        # Но это не всегда верно.
                        # Лучше в search_packaged_items возвращать (тип, qr_data/артикул, fio, дата1, дата2)
                        # Переделаем search_packaged_items
                        
                        # В текущем виде search_packaged_items возвращает:
                        # для Упаковки: (qr_data, fio, created, modified)
                        # для Аутсорсинга: (артикул, fio, дата_заявки, дата_получения)
                        # Мы можем проверить, есть ли qr_data в таблице аутсорсинг
                        conn = sqlite3.connect("/home/viktor/freedom/workshop_data_1.db")
                        cursor = conn.cursor()
                        cursor.execute('SELECT "артикул" FROM "аутсорсинг" WHERE "артикул" = ?', (qr_data,))
                        is_outsourcing = cursor.fetchone() is not None
                        conn.close()
                        
                        if is_outsourcing:
                            workshop = "Упаковка (аутсорсинг)"
                            date = modified if modified else "-" # дата получения
                        else:
                            workshop = "Упаковка"
                            date = created if created else "-" # дата запуска

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

# === ЗАГЛУШКИ ДЛЯ КНОПОК (возвращаются позже) ===
async def packaging_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📦 Временно недоступно. Используйте ввод номера заказа.")
    return ConversationHandler.END

async def zakladki_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🔖 Временно недоступно. Используйте ввод номера заказа.")
    return ConversationHandler.END

async def reklamacia_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⚠️ Временно недоступно. Используйте ввод номера заказа.")
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
        "⚠️ *Рекламация:* нажмите и введите заказ\n\n"
        "💡 *Примечание:* Закладные и рекламации не показываются, если изделие уже упаковано."
    )
    keyboard = [[KeyboardButton("Упаковка"), KeyboardButton("Закладные")], [KeyboardButton("Рекламация")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Регистрация
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAITING_FOR_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name_input)]},
        fallbacks=[],
        allow_reentry=True
    )

    # Добавляем обработчики
    application.add_handler(registration_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == '__main__':
    main()
