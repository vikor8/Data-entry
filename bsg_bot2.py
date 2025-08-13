#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BSG Аналитик - Telegram бот для анализа данных из базы данных workshop_data.db.
"""
import logging
import sqlite3
import re
from collections import defaultdict
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
# === НАСТРОЙКИ ===
# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# Токен бота (используем предоставленный токен)
TOKEN = "8414355250:AAGyGpcYMIGgeR6hKAF35niRT0HE06zyke4"
# Путь к базе данных, созданной первым ботом
DB_PATH = "/srv/dev-disk-by-uuid-6cbacaea-af88-4ced-8990-f4f163606aae/home/bot/workshop_data.db"
# Имя таблицы участка упаковки
PACKAGING_TABLE_NAME = "Участок_упаковки"
# === ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ ===
def get_table_names():
    """Получает список имен таблиц из базы данных."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        logger.info(f"Найдено таблиц: {len(tables)}")
        return tables
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка таблиц: {e}")
        return []
def search_by_order(order_number: str):
    """
    Ищет все изделия по номеру заказа во всех таблицах.
    Возвращает словарь: {участок: [(qr_data, creation_date, modification_date), ...]}
    """
    results = defaultdict(list)
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Создаем паттерн для поиска qr_data, начинающихся с номера заказа и точки
    pattern = f"{order_number}.%"
    for table in tables:
        try:
            cursor.execute(f'''
                SELECT qr_data, creation_date, modification_date 
                FROM "{table}" 
                WHERE qr_data LIKE ?
            ''', (pattern,))
            rows = cursor.fetchall()
            if rows:
                # Преобразуем имя таблицы обратно в читаемый формат
                readable_workshop = table.replace("_", " ")
                results[readable_workshop].extend(rows)
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")
    conn.close()
    logger.info(f"Поиск по заказу {order_number}: найдено в {len(results)} участках")
    return results
def search_by_item(item_number: str):
    """
    Ищет конкретное изделие по его полному номеру во всех таблицах.
    Возвращает список: [(участок, qr_data, creation_date, modification_date)]
    """
    results = []
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for table in tables:
        try:
            cursor.execute(f'''
                SELECT qr_data, creation_date, modification_date 
                FROM "{table}" 
                WHERE qr_data = ?
            ''', (item_number,))
            rows = cursor.fetchall()
            if rows:
                readable_workshop = table.replace("_", " ")
                for row in rows:
                    results.append((readable_workshop, row[0], row[1], row[2]))
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")
    conn.close()
    logger.info(f"Поиск по изделию {item_number}: найдено {len(results)} записей")
    return results

def search_packaged_items(order_number: str):
    """
    Ищет все изделия по номеру заказа, которые прошли через участок упаковки.
    Возвращает список: [(qr_data, creation_date, modification_date)]
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Создаем паттерн для поиска qr_data, начинающихся с номера заказа и точки
        pattern = f"{order_number}.%"
        cursor.execute(f'''
            SELECT qr_data, creation_date, modification_date 
            FROM "{PACKAGING_TABLE_NAME}" 
            WHERE qr_data LIKE ?
        ''', (pattern,))
        rows = cursor.fetchall()
        conn.close()
        logger.info(f"Поиск упакованных изделий по заказу {order_number}: найдено {len(rows)} записей")
        return rows
    except sqlite3.Error as e:
        logger.error(f"Ошибка при поиске упакованных изделий по заказу {order_number}: {e}")
        return []

def format_table_data(data, headers):
    """
    Форматирует данные в виде таблицы с использованием моноширинного шрифта.
    """
    if not data:  # Исправлено: добавлено условие проверки data
        return ""
    
    # Рассчитываем максимальную ширину для каждого столбца
    col_widths = [len(str(header)) for header in headers]
    for row in data:  # Исправлено: убрана лишняя проверка, так как мы уже проверили data выше
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Создаем строку форматирования
    format_str = " │ ".join(["{:<" + str(width) + "}" for width in col_widths])
    
    # Создаем таблицу
    table_lines = []
    # Заголовок
    table_lines.append(format_str.format(*headers))
    # Разделитель
    separator = "─┼─".join(["─" * width for width in col_widths])
    table_lines.append(separator)
    # Данные
    for row in data:
        table_lines.append(format_str.format(*[str(cell) for cell in row]))
    
    return "```\n" + "\n".join(table_lines) + "\n```"
# === ОБРАБОТЧИКИ СООБЩЕНИЙ TELEGRAM ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    welcome_text = (
        "🤖 *BSG Аналитик*\n\n"
        "🔍 Я предоставляю информацию о заказах и изделиях.\n\n"
        "📤 *Как пользоваться:*\n"
        "• Введите *номер заказа* (например, `123` или `123/1` или `123_1`)\n"
        "• Введите *номер изделия* (например, `123.45` или `123/1.05` или `123_1.05`)\n"
        "• Используйте /packaged_items `<номер_заказа>` для поиска упакованных изделий\n"
        "• Используйте /help для справки\n"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочную информацию при команде /help."""
    help_text = (
        "📖 *Справка BSG Аналитик*\n\n"
        "🔎 *Поиск по заказу:*\n"
        "Отправьте номер заказа (например, `123`, `123/1`, `123_1`).\n"
        "Бот покажет все изделия из этого заказа по всем участкам.\n\n"
        "🔎 *Поиск по изделию:*\n"
        "Отправьте полный номер изделия (например, `123.45`, `123/1.05`, `123_1.05`).\n"
        "Бот покажет, на каких участках это изделие было запущено.\n\n"
        "📦 *Поиск упакованных изделий:*\n"
        "Используйте команду `/packaged_items <номер_заказа>` (например, `/packaged_items 123` или `/packaged_items 123/1`).\n"
        "Бот покажет все изделия из этого заказа, прошедшие через участок упаковки.\n\n"
        "❌ *Если данные не найдены:*\n"
        "Бот ответит: _\"Не запускали в работу\"_."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def packaged_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет список изделий из заказа, прошедших через участок упаковки."""
    # Проверяем, передан ли аргумент с номером заказа
    if not context.args:
        await update.message.reply_text(
            "❗ Пожалуйста, укажите номер заказа после команды.\n"
            "Пример: `/packaged_items 123` или `/packaged_items 123/1`",
            parse_mode='Markdown'
        )
        return
    
    order_number = context.args[0].strip()
    
    # Проверка формата ввода: допускаем цифры, слэши и подчеркивания
    if not re.match(r'^[\d/_]+$', order_number):
        await update.message.reply_text(
            "❗ Пожалуйста, введите корректный номер заказа (цифры, слэши и подчеркивания).\n"
            "Пример: `/packaged_items 123` или `/packaged_items 123/1`",
            parse_mode='Markdown'
        )
        return
    
    logger.info(f"Выполняется поиск упакованных изделий по заказу: {order_number}")
    
    try:
        packaged_results = search_packaged_items(order_number)
        
        if not packaged_results:
            await update.message.reply_text("📭 _Не запускали в работу или нет упакованных изделий_", parse_mode='Markdown')
            return
        
        # Формируем таблицу для упакованных изделий
        headers = ["Изделие", "Запущено", "Изменено"]
        table_data = []
        for qr_data, creation_date, modification_date in packaged_results:
            # Форматируем даты
            creation_short = creation_date.split()[0] if creation_date else "-"
            modification_short = modification_date.split()[0] if modification_date else "-"
            table_data.append([qr_data, creation_short, modification_short])
        
        table_str = format_table_data(table_data, headers)
        response = f"📦 *Упакованные изделия заказа {order_number}:*\n\n{table_str}"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса '/packaged_items {order_number}': {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.",
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения пользователя."""
    user_input = update.message.text.strip()
    logger.info(f"Получен запрос от пользователя: '{user_input}'")
    # Проверка формата ввода: допускаем цифры, точки, слэши и подчеркивания
    if not re.match(r'^[\d./_]+$', user_input):
        await update.message.reply_text(
            "❗ Пожалуйста, введите корректный номер заказа (например, `123`, `123/1`, `123_1`) или изделия (например, `123.45`, `123/1.05`, `123_1.05`).",
            parse_mode='Markdown'
        )
        return
    # Определяем, что ввел пользователь: заказ или изделие
    # Если содержит точку и после точки есть цифры - это изделие
    is_item_search = '.' in user_input and user_input.split('.')[-1].isdigit()
    try:
        if is_item_search:
            # === Поиск по номеру изделия ===
            logger.info(f"Выполняется поиск по изделию: {user_input}")
            item_results = search_by_item(user_input)
            if not item_results:
                await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
                return
            # Формируем таблицу для результатов по изделию
            headers = ["Участок", "Запущено", "Изменено"]
            table_data = []
            for workshop, qr_data, creation_date, modification_date in item_results:
                # Форматируем даты (берем только дату без времени для компактности)
                creation_short = creation_date.split()[0] if creation_date else "-"
                modification_short = modification_date.split()[0] if modification_date else "-"
                table_data.append([workshop, creation_short, modification_short])
            table_str = format_table_data(table_data, headers)
            response = f"📋 *Информация об изделии {user_input}:*\n\n{table_str}"
        else:
            # === Поиск по номеру заказа ===
            logger.info(f"Выполняется поиск по заказу: {user_input}")
            order_results = search_by_order(user_input)
            if not order_results:
                await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
                return
            # Собираем все уникальные изделия для отображения в конце
            all_items = set()
            # Формируем таблицы для каждого участка
            response = f"📦 *Информация по заказу {user_input}:*\n\n"
            for workshop, items in order_results.items():
                response += f"📍 *{workshop}*\n"
                # Создаем таблицу для изделий на этом участке
                headers = ["Изделие", "Запущено", "Изменено"]
                table_data = []
                for qr_data, creation_date, modification_date in items:
                    # Добавляем изделие в общий список
                    all_items.add(qr_data)
                    # Форматируем даты
                    creation_short = creation_date.split()[0] if creation_date else "-"
                    modification_short = modification_date.split()[0] if modification_date else "-"
                    table_data.append([qr_data, creation_short, modification_short])
                table_str = format_table_data(table_data, headers)
                response += f"{table_str}\n\n"
            # Добавляем список всех изделий в конце
            if all_items:
                sorted_items = sorted(all_items, key=lambda x: [int(i) if i.isdigit() else i for i in x.split('.')])
                items_list = "\n".join([f"• `{item}`" for item in sorted_items])
                response += f"*Все изделия заказа {user_input}:*\n{items_list}"
        # Отправляем ответ пользователю
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса '{user_input}': {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.",
            parse_mode='Markdown'
        )
# === ГЛАВНАЯ ФУНКЦИЯ ===
def main() -> None:
    """Запуск бота."""
    logger.info("Инициализация бота BSG Аналитик...")
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("packaged_items", packaged_items_command)) # Новый обработчик
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен. Ожидание сообщений...")
    # Запускаем бота
    application.run_polling()
if __name__ == '__main__':
    main()
