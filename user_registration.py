#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль регистрации пользователей для BSG Аналитик бота
"""
import logging
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

# Настройка логирования
logger = logging.getLogger(__name__)

# Состояния для регистрации
WAITING_FOR_FULL_NAME = 1

# Путь к базе данных (должен совпадать с основным ботом)
DB_PATH = "/home/viktor/Data-entry/workshop_data_1.db"
def is_user_registered(telegram_id):
    """Проверяет, зарегистрирован ли пользователь в базе данных."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"Ошибка в is_user_registered: {e}")
        return False

def register_user(telegram_id, full_name):
    """Регистрирует нового пользователя в базе данных."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Вставляем пользователя в таблицу users
        cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, full_name) 
            VALUES (?, ?)
        ''', (telegram_id, full_name))
        
        # Вставляем дату создания пользователя
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT OR IGNORE INTO user_creation_dates (telegram_id, created_at)
            VALUES (?, ?)
        ''', (telegram_id, current_time))
        
        conn.commit()
        conn.close()
        logger.info(f"Пользователь {full_name} (ID: {telegram_id}) зарегистрирован")
        return True
    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя: {e}")
        return False

def get_user_full_name(telegram_id):
    """Получение Ф.И.О. пользователя по telegram_id из таблицы users"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT full_name FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "-"
    except Exception as e:
        logger.error(f"Ошибка в get_user_full_name: {e}")
        return "-"

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
            "• Используйте /help для справки"
        )
        await update.message.reply_text(success_text, parse_mode='Markdown')
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
