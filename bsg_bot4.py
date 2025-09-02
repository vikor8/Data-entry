#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BSG Аналитик - Telegram бот для анализа данных из базы данных workshop_data_1.db.
"""
import logging
import re
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
    get_user_full_name
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

# Состояния для регистрации
WAITING_FOR_FULL_NAME = 1
# Состояния для поиска упакованных изделий
WAITING_FOR_ORDER_NUMBER = 2

def format_table_data(data, headers):
    """
    Форматирует данные в виде таблицы с использованием моноширинного шрифта.
    """
    if not data:
        return ""
    
    # Рассчитываем максимальную ширину для каждого столбца
    col_widths = [len(str(header)) for header in headers]
    for row in data:
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

# === ОБРАБОТЧИКИ РЕГИСТРАЦИИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение при команде /start и проверяет регистрацию."""
    telegram_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username or "Пользователь"
    
    # Проверяем, зарегистрирован ли пользователь
    if is_user_registered(telegram_id):
        full_name = get_user_full_name(telegram_id)
        welcome_text = (
            f"🤖 *BSG Аналитик*, {full_name}!\n\n"
            "🔍 Я предоставляю информацию о заказах и изделиях.\n\n"
            "📤 *Как пользоваться:*\n"
            "• Введите *номер заказа* (например, `152/1` или `123`)\n"
            "• Введите *номер изделия* (например, `152/1.28` или `123.45`)\n"
            "• Используйте кнопку *'Упаковка'* для поиска упакованных изделий\n"
            "• Используйте /help для справки\n"
        )
        
        # Создаем клавиатуру с кнопкой "Упаковка"
        keyboard = [[KeyboardButton("Упаковка")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        # Начинаем регистрацию
        context.user_data['telegram_id'] = telegram_id
        registration_text = (
            f"👋 Привет, {user_name}!\n\n"
            "Для работы с ботом необходима регистрация.\n"
            "Пожалуйста, введите ваше *Ф.И.О.* в формате:\n"
            "`Иванов Иван Иванович`\n\n"
            "Или в формате с инициалами:\n"
            "`Иванов И.И.`"
        )
        await update.message.reply_text(registration_text, parse_mode='Markdown')
        return WAITING_FOR_FULL_NAME

async def handle_full_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод Ф.И.О. пользователя."""
    full_name = update.message.text.strip()
    
    # Проверка формата Ф.И.О.
    if not full_name or len(full_name.split()) < 2:
        await update.message.reply_text(
            "❌ Неверный формат Ф.И.О.\n\n"
            "Пожалуйста, введите ваше *Ф.И.О.* в одном из форматов:\n"
            "• `Иванов Иван Иванович`\n"
            "• `Иванов И.И.`\n\n"
            "Попробуйте еще раз:"
        )
        return WAITING_FOR_FULL_NAME
    
    telegram_id = context.user_data.get('telegram_id')
    if not telegram_id:
        await update.message.reply_text("❌ Ошибка регистрации. Пожалуйста, начните сначала с помощью /start")
        return ConversationHandler.END
    
    # Регистрируем пользователя
    if register_user(telegram_id, full_name):
        success_text = (
            f"✅ *Регистрация завершена!*\n\n"
            f"Добро пожаловать, {full_name}!\n\n"
            "🔍 Теперь вы можете использовать все функции бота:\n"
            "• Введите *номер заказа* для поиска\n"
            "• Введите *номер изделия* для анализа\n"
            "• Используйте кнопку *'Упаковка'* для поиска упакованных изделий\n"
            "• Используйте /help для справки"
        )
        
        # Создаем клавиатуру с кнопкой "Упаковка"
        keyboard = [[KeyboardButton("Упаковка")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Ошибка при регистрации. Попробуйте позже или обратитесь к администратору."
        )
        return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена регистрации."""
    await update.message.reply_text(
        "❌ Регистрация отменена.\n"
        "Для начала работы с ботом используйте команду /start"
    )
    return ConversationHandler.END

# === ОБРАБОТЧИКИ ДЛЯ УПАКОВКИ ===

async def packaging_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик нажатия кнопки 'Упаковка'"""
    telegram_id = update.effective_user.id
    
    # Проверяем регистрацию
    if not is_user_registered(telegram_id):
        await update.message.reply_text(
            "❌ Для использования бота необходима регистрация.\n"
            "Пожалуйста, начните с команды /start"
        )
        return ConversationHandler.END
    
    # Запрашиваем номер заказа
    await update.message.reply_text(
        "📦 *Поиск упакованных изделий*\n\n"
        "Пожалуйста, введите номер заказа для поиска упакованных изделий.\n"
        "Пример: `152/1` или `123`",
        parse_mode='Markdown'
    )
    return WAITING_FOR_ORDER_NUMBER

async def handle_packaging_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод номера заказа для поиска упакованных изделий"""
    telegram_id = update.effective_user.id
    order_number = update.message.text.strip()
    
    # Проверка формата ввода: допускаем цифры, слэши и подчеркивания
    if not re.match(r'^[\d/_]+$', order_number):
        await update.message.reply_text(
            "❗ Пожалуйста, введите корректный номер заказа (цифры, слэши и подчеркивания).\n"
            "Пример: `152/1` или `123`",
            parse_mode='Markdown'
        )
        return WAITING_FOR_ORDER_NUMBER
    
    logger.info(f"Выполняется поиск упакованных изделий по заказу: {order_number}")
    
    try:
        packaged_results = search_packaged_items(order_number)
        
        if not packaged_results:
            await update.message.reply_text("📭 _Не запускали в работу или нет упакованных изделий_", parse_mode='Markdown')
            return ConversationHandler.END
        
        # Формируем таблицу для упакованных изделий
        headers = ["Изделие", "Фамилия", "Запущено", "Изменено"]
        table_data = []
        for qr_data, telegram_id, creation_date, modification_date in packaged_results:
            # Получаем Ф.И.О. пользователя
            full_name = get_user_full_name(telegram_id)
            # Форматируем даты
            creation_short = creation_date.split()[0] if creation_date else "-"
            modification_short = modification_date.split()[0] if modification_date else "-"
            table_data.append([qr_data, full_name, creation_short, modification_short])
        
        table_str = format_table_data(table_data, headers)
        response = f"📦 *Упакованные изделия заказа {order_number}:*\n\n{table_str}"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса упаковки для заказа {order_number}: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

# === ОСНОВНЫЕ ОБРАБОТЧИКИ ===

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочную информацию при команде /help."""
    telegram_id = update.effective_user.id
    
    # Проверяем регистрацию
    if not is_user_registered(telegram_id):
        await update.message.reply_text(
            "❌ Для использования бота необходима регистрация.\n"
            "Пожалуйста, начните с команды /start"
        )
        return
    
    help_text = (
        "📖 *Справка BSG Аналитик*\n\n"
        "🔎 *Поиск по заказу:*\n"
        "Отправьте номер заказа (например, `152/1`, `123`).\n"
        "Бот покажет все изделия из этого заказа по всем участкам.\n\n"
        "🔎 *Поиск по изделию:*\n"
        "Отправьте полный номер изделия (например, `152/1.28`, `123.45`).\n"
        "Бот покажет, на каких участках это изделие было запущено.\n\n"
        "📦 *Поиск упакованных изделий:*\n"
        "Нажмите кнопку *'Упаковка'* и введите номер заказа.\n"
        "Бот покажет все изделия из этого заказа, прошедшие через участок упаковки.\n\n"
        "❌ *Если данные не найдены:*\n"
        "Бот ответит: _\"Не запускали в работу\"_."
    )
    
    # Создаем клавиатуру с кнопкой "Упаковка"
    keyboard = [[KeyboardButton("Упаковка")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения пользователя."""
    telegram_id = update.effective_user.id
    
    # Проверяем регистрацию
    if not is_user_registered(telegram_id):
        await update.message.reply_text(
            "❌ Для использования бота необходима регистрация.\n"
            "Пожалуйста, начните с команды /start"
        )
        return
    
    user_input = update.message.text.strip()
    logger.info(f"Получен запрос от пользователя: '{user_input}'")
    
    # Проверяем, не нажата ли кнопка "Упаковка"
    if user_input == "Упаковка":
        await packaging_button_handler(update, context)
        return
    
    # Проверка формата ввода: допускаем цифры, точки, слэши и подчеркивания
    if not re.match(r'^[\d./_]+$', user_input):
        await update.message.reply_text(
            "❗ Пожалуйста, введите корректный номер заказа (например, `152/1`, `123`) или изделия (например, `152/1.28`, `123.45`).",
            parse_mode='Markdown'
        )
        return
    
    # Определяем, что ввел пользователь: заказ или изделие
    # Если содержит точку и после точки есть цифры - это изделие
    is_item_search = '.' in user_input and re.search(r'\.(\d+)', user_input)
    
    try:
        if is_item_search:
            # === Поиск по номеру изделия ===
            logger.info(f"Выполняется поиск по изделию: {user_input}")
            item_results = search_by_item(user_input)
            if not item_results:
                await update.message.reply_text("📭 _Не запускали в работу_", parse_mode='Markdown')
                return
            
            # Формируем таблицу для результатов по изделию
            headers = ["Участок", "Фамилия", "Запущено", "Изменено"]
            table_data = []
            for workshop, qr_data, telegram_id, creation_date, modification_date in item_results:
                # Получаем Ф.И.О. пользователя
                full_name = get_user_full_name(telegram_id)
                # Форматируем даты
                creation_short = creation_date.split()[0] if creation_date else "-"
                modification_short = modification_date.split()[0] if modification_date else "-"
                table_data.append([workshop, full_name, creation_short, modification_short])
            
            table_str = format_table_data(table_data, headers)
            response = f"🔧 *Информация об изделии {user_input}:*\n\n{table_str}"
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
            response = f"📊 *Информация по заказу {user_input}:*\n\n"
            
            for workshop, items in order_results.items():
                response += f"📍 *{workshop}*\n"
                # Создаем таблицу для изделий на этом участке
                headers = ["Изделие", "Фамилия", "Запущено", "Изменено"]
                table_data = []
                for qr_data, telegram_id, creation_date, modification_date in items:
                    # Добавляем изделие в общий список
                    all_items.add(qr_data)
                    # Получаем Ф.И.О. пользователя
                    full_name = get_user_full_name(telegram_id)
                    # Форматируем даты
                    creation_short = creation_date.split()[0] if creation_date else "-"
                    modification_short = modification_date.split()[0] if modification_date else "-"
                    table_data.append([qr_data, full_name, creation_short, modification_short])
                
                table_str = format_table_data(table_data, headers)
                response += f"{table_str}\n\n"
            
            # Добавляем список всех изделий в конце
            if all_items:
                sorted_items = sorted(all_items)
                items_list = "\n".join([f"• `{item}`" for item in sorted_items])
                response += f"*📋 Все изделия заказа {user_input}:*\n{items_list}"
        
        # Отправляем ответ пользователю
        # Проверяем длину сообщения
        if len(response) > 4096:
            response = response[:4000] + "\n\n... (сообщение слишком длинное)"
        
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
    
    # Создаем ConversationHandler для регистрации
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True
    )
    
    # Создаем ConversationHandler для поиска упакованных изделий
    packaging_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Упаковка$"), packaging_button_handler)],
        states={
            WAITING_FOR_ORDER_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_packaging_order_input)
            ],
        },
        fallbacks=[],
        allow_reentry=True
    )
    
    # Добавляем обработчики
    application.add_handler(registration_handler)
    application.add_handler(packaging_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен. Ожидание сообщений...")
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
