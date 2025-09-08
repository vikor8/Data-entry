#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BSG Аналитик - Telegram бот для анализа данных из базы данных workshop_data_1.db.
"""

import logging
import re
import sqlite3  # ✅ Обязательно импортируем
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
    get_table_names
)

# === НАСТРОЙКИ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8414355250:AAGyGpcYMIGgeR6hKAF35niRT0HE06zyke4"

# Состояния
WAITING_FOR_FULL_NAME = 1
WAITING_FOR_PACKAGING_ORDER = 2
WAITING_FOR_ZAKLADKI_ORDER = 3
WAITING_FOR_REKLAMACIA_ORDER = 4

# === Форматирование таблицы ===
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

# === ОБРАБОТЧИКИ РЕГИСТРАЦИИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие и проверка регистрации."""
    telegram_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username or "Пользователь"

    if is_user_registered(telegram_id):
        full_name = get_user_full_name(telegram_id)
        welcome_text = (
            f"🤖 *BSG Аналитик*, {full_name}!\n\n"
            "🔍 Я предоставляю информацию о заказах и изделиях.\n\n"
            "📤 *Как пользоваться:*\n"
            "• Введите *номер заказа* (например, `152/1`)\n"
            "• Введите *номер изделия* (например, `152/1.28`)\n"
            "• Используйте кнопки *'Упаковка'*, *'Закладные'*, *'Рекламация'*\n"
            "• Используйте /help для справки\n"
        )

        keyboard = [
            [KeyboardButton("Упаковка"), KeyboardButton("Закладные")],
            [KeyboardButton("Рекламация")]
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

async def handle_full_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка Ф.И.О."""
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
            [KeyboardButton("Рекламация")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Ошибка при регистрации.")
        return ConversationHandler.END

# === УПАКОВКА ===

async def packaging_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос номера заказа для упакованных изделий."""
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return ConversationHandler.END

    await update.message.reply_text(
        "📦 *Поиск упакованных изделий*\n\n"
        "Введите номер заказа (например, `152/1`):",
        parse_mode='Markdown'
    )
    return WAITING_FOR_PACKAGING_ORDER

async def handle_packaging_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода заказа для упаковки."""
    order_number = update.message.text.strip()
    if not re.match(r'^[\d/_]+$', order_number):
        await update.message.reply_text("❗ Введите корректный номер заказа.")
        return WAITING_FOR_PACKAGING_ORDER

    packaged_results = search_packaged_items(order_number)
    if not packaged_results:
        await update.message.reply_text("📭 _Нет упакованных изделий_", parse_mode='Markdown')
        return ConversationHandler.END

    headers = ["Изделие", "Фамилия", "Запущено", "Изменено"]
    table_data = []
    for qr_data, telegram_id, creation_date, modification_date in packaged_results:
        full_name = get_user_full_name(telegram_id)
        creation_short = creation_date.split()[0] if creation_date else "-"
        modification_short = modification_date.split()[0] if modification_date else "-"
        table_data.append([qr_data, full_name, creation_short, modification_short])

    table_str = format_table_data(table_data, headers)
    response = f"📦 *Упакованные изделия заказа {order_number}:*\n\n{table_str}"
    await update.message.reply_text(response, parse_mode='Markdown')
    return ConversationHandler.END

# === ЗАКЛАДНЫЕ (только если НЕ упакованы) ===

async def zakladki_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос номера заказа для закладных."""
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return ConversationHandler.END

    await update.message.reply_text(
        "🔖 *Поиск активных закладных*\n\n"
        "Введите номер заказа (например, `152/1`):",
        parse_mode='Markdown'
    )
    return WAITING_FOR_ZAKLADKI_ORDER

async def handle_zakladki_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода заказа для закладных: активные и упакованные."""
    order_number = update.message.text.strip()
    if not re.match(r'^[\d/_]+$', order_number):
        await update.message.reply_text("❗ Введите корректный номер заказа.")
        return WAITING_FOR_ZAKLADKI_ORDER

    try:
        conn = sqlite3.connect("/home/viktor/freedom/workshop_data_1.db")
        cursor = conn.cursor()
        tables = get_table_names()
        pattern = f"{order_number}%"

        # Получаем упакованные изделия
        cursor.execute('SELECT qr_data FROM "Участок_упаковки" WHERE qr_data LIKE ?', (pattern,))
        packaged_items = {row[0] for row in cursor.fetchall()}

        # Собираем все закладные
        all_zakladki = []
        for table in tables:
            if table == "Участок_упаковки":
                continue
            try:
                cursor.execute(f'''
                    SELECT qr_data, telegram_id, creation_date, modification_date 
                    FROM "{table}" 
                    WHERE qr_data LIKE ? AND тип_изделия_id = 2
                ''', (pattern,))
                rows = cursor.fetchall()
                for row in rows:
                    readable_workshop = table.replace("_", " ")
                    all_zakladki.append((row[0], readable_workshop, row[1], row[2], row[3]))
            except sqlite3.Error as e:
                logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

        conn.close()

        # Фильтруем
        active = [item for item in all_zakladki if item[0] not in packaged_items]
        packed = [item for item in all_zakladki if item[0] in packaged_items]

        # Формируем ответ
        response = f"🔖 *Закладные заказа {order_number}*\n\n"

        # Активные
        if active:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = [
                [qr, workshop, get_user_full_name(tid), (cd or "").split()[0] if cd else "-"]
                for qr, workshop, tid, cd, _ in active
            ]
            table_str = format_table_data(table_data, headers)
            response += f"📌 *Активные (не упакованы)*:\n{table_str}\n"
        else:
            response += "📌 *Активные (не упакованы)*: _нет_\n\n"

        # Упакованные
        if packed:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = [
                [qr, workshop, get_user_full_name(tid), (cd or "").split()[0] if cd else "-"]
                for qr, workshop, tid, cd, _ in packed
            ]
            table_str = format_table_data(table_data, headers)
            response += f"📦 *Уже упакованы*:\n{table_str}\n"
        else:
            response += "📦 *Уже упакованы*: _нет_\n"

        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Ошибка при поиске закладных: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке запроса.")
        return ConversationHandler.END

# === РЕКЛАМАЦИИ (только если НЕ упакованы) ===

async def reklamacia_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос номера заказа для рекламаций."""
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚠️ *Поиск активных рекламаций*\n\n"
        "Введите номер заказа (например, `152/1`):",
        parse_mode='Markdown'
    )
    return WAITING_FOR_REKLAMACIA_ORDER

async def handle_reklamacia_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода заказа для рекламаций: активные и упакованные."""
    order_number = update.message.text.strip()
    if not re.match(r'^[\d/_]+$', order_number):
        await update.message.reply_text("❗ Введите корректный номер заказа.")
        return WAITING_FOR_REKLAMACIA_ORDER

    try:
        conn = sqlite3.connect("/home/viktor/freedom/workshop_data_1.db")
        cursor = conn.cursor()
        tables = get_table_names()
        pattern = f"{order_number}%"

        # Получаем упакованные изделия
        cursor.execute('SELECT qr_data FROM "Участок_упаковки" WHERE qr_data LIKE ?', (pattern,))
        packaged_items = {row[0] for row in cursor.fetchall()}

        # Собираем все рекламации
        all_reklamacii = []
        for table in tables:
            if table == "Участок_упаковки":
                continue
            try:
                cursor.execute(f'''
                    SELECT qr_data, telegram_id, creation_date, modification_date 
                    FROM "{table}" 
                    WHERE qr_data LIKE ? AND тип_изделия_id = 3
                ''', (pattern,))
                rows = cursor.fetchall()
                for row in rows:
                    readable_workshop = table.replace("_", " ")
                    all_reklamacii.append((row[0], readable_workshop, row[1], row[2], row[3]))
            except sqlite3.Error as e:
                logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

        conn.close()

        # Фильтруем
        active = [item for item in all_reklamacii if item[0] not in packaged_items]
        packed = [item for item in all_reklamacii if item[0] in packaged_items]

        # Формируем ответ
        response = f"⚠️ *Рекламации заказа {order_number}*\n\n"

        # Активные
        if active:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = [
                [qr, workshop, get_user_full_name(tid), (cd or "").split()[0] if cd else "-"]
                for qr, workshop, tid, cd, _ in active
            ]
            table_str = format_table_data(table_data, headers)
            response += f"📌 *Активные (не упакованы)*:\n{table_str}\n"
        else:
            response += "📌 *Активные (не упакованы)*: _нет_\n\n"

        # Упакованные
        if packed:
            headers = ["Изделие", "Участок", "Фамилия", "Запущено"]
            table_data = [
                [qr, workshop, get_user_full_name(tid), (cd or "").split()[0] if cd else "-"]
                for qr, workshop, tid, cd, _ in packed
            ]
            table_str = format_table_data(table_data, headers)
            response += f"📦 *Уже упакованы*:\n{table_str}\n"
        else:
            response += "📦 *Уже упакованы*: _нет_\n"

        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Ошибка при поиске рекламаций: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке запроса.")
        return ConversationHandler.END

# === СПРАВКА ===

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Справка."""
    telegram_id = update.effective_user.id
    if not is_user_registered(telegram_id):
        await update.message.reply_text("❌ Зарегистрируйтесь через /start")
        return

    help_text = (
        "📖 *Справка BSG Аналитик*\n\n"
        "🔍 *Поиск по заказу:* `152/1`\n"
        "🔍 *Поиск по изделию:* `152/1.28`\n"
        "📦 *Упаковка:* нажмите и введите заказ\n"
        "🔖 *Закладные:* нажмите и введите заказ\n"
        "⚠️ *Рекламация:* нажмите и введите заказ\n\n"
        "💡 *Примечание:* Закладные и рекламации не показываются, если изделие уже упаковано."
    )
    keyboard = [
        [KeyboardButton("Упаковка"), KeyboardButton("Закладные")],
        [KeyboardButton("Рекламация")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

# === ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текста и кнопок."""
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

    if not re.match(r'^[\d./_]+$', user_input):
        await update.message.reply_text("❗ Введите номер заказа или изделия.")
        return

    is_item_search = '.' in user_input and re.search(r'\.(\d+)', user_input)

    try:
        if is_item_search:
            item_results = search_by_item(user_input)
            if not item_results:
                await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
                return
            headers = ["Участок", "Фамилия", "Запущено", "Изменено"]
            table_data = [[w, get_user_full_name(t), c.split()[0] if c else "-", m.split()[0] if m else "-"] for w, _, t, c, m in item_results]
            table_str = format_table_data(table_data, headers)
            response = f"🔧 *Информация об изделии {user_input}:*\n\n{table_str}"
        else:
            order_results = search_by_order(user_input)
            if not order_results:
                await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
                return
            response = f"📊 *Информация по заказу {user_input}:*\n\n"
            all_items = set()
            for workshop, items in order_results.items():
                response += f"📍 *{workshop}*\n"
                headers = ["Изделие", "Фамилия", "Запущено", "Изменено"]
                table_data = [[q, get_user_full_name(t), c.split()[0] if c else "-", m.split()[0] if m else "-"] for q, t, c, m in items]
                table_str = format_table_data(table_data, headers)
                response += f"{table_str}\n\n"
                all_items.update(q for q, _, _, _ in items)
            if all_items:
                items_list = "\n".join([f"• `{item}`" for item in sorted(all_items)])
                response += f"*📋 Все изделия заказа {user_input}:*\n{items_list}"

        if len(response) > 4096:
            response = response[:4000] + "\n\n... (сообщение слишком длинное)"

        await update.message.reply_text(response, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке запроса.")

# === ГЛАВНАЯ ФУНКЦИЯ ===

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Конвёрсии
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAITING_FOR_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name_input)]},
        fallbacks=[],
        allow_reentry=True
    )

    packaging_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Упаковка$"), packaging_button_handler)],
        states={WAITING_FOR_PACKAGING_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_packaging_order_input)]},
        fallbacks=[],
        allow_reentry=True
    )

    zakladki_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Закладные$"), zakladki_button_handler)],
        states={WAITING_FOR_ZAKLADKI_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_zakladki_order_input)]},
        fallbacks=[],
        allow_reentry=True
    )

    reklamacia_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Рекламация$"), reklamacia_button_handler)],
        states={WAITING_FOR_REKLAMACIA_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reklamacia_order_input)]},
        fallbacks=[],
        allow_reentry=True
    )

    # Добавляем обработчики
    application.add_handler(registration_handler)
    application.add_handler(packaging_handler)
    application.add_handler(zakladki_handler)
    application.add_handler(reklamacia_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == '__main__':
    main()
