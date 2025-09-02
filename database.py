#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных для BSG Аналитик бота (обновлён с поддержкой аутсорсинга)
"""
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = "/home/viktor/freedom/workshop_data_1.db"

# Имя таблицы участка упаковки
PACKAGING_TABLE_NAME = "Участок_упаковки"

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
    Ищет все изделия по номеру заказа во всех таблицах, включая аутсорсинг.
    Возвращает словарь: {участок: [(qr_data, telegram_id, creation_date, modification_date), ...]}
    Для аутсорсинга:
        - если есть дата_заявки → добавляется в 'Аутсорсинг' как "отправлен на аутсорс"
        - если есть дата_получения → не добавляется (уже в упаковке)
    """
    results = defaultdict(list)
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Паттерн для поиска по заказу
    pattern = f"{order_number}%"

    # === 1. Поиск в обычных таблицах ===
    for table in tables:
        if table in ['users', 'user_creation_dates', 'аутсорсинг']:
            continue

        try:
            cursor.execute(f'''
                SELECT qr_data, telegram_id, creation_date, modification_date 
                FROM "{table}" 
                WHERE qr_data LIKE ?
            ''', (pattern,))
            rows = cursor.fetchall()
            if rows:
                readable_workshop = table.replace("_", " ")
                results[readable_workshop].extend(rows)
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

    # === 2. Поиск в таблице "аутсорсинг" ===
    try:
        cursor.execute('''
            SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
            FROM "аутсорсинг"
            WHERE "артикул" LIKE ?
        ''', (pattern,))
        rows = cursor.fetchall()
        for артикул, аутсорсер, дата_заявки, дата_получения in rows:
            if дата_заявки and not дата_получения:
                # Отправлен на аутсорс → добавляем в "Аутсорсинг"
                results["Аутсорсинг"].append((
                    артикул,
                    аутсорсер,
                    дата_заявки,
                    None  # modification_date не используется
                ))
            # Если уже получен — не показываем в "Аутсорсинг", но может быть в "Упаковке"
    except sqlite3.Error as e:
        logger.error(f"Ошибка при запросе к таблице 'аутсорсинг': {e}")

    conn.close()
    logger.info(f"Поиск по заказу {order_number}: найдено в {len(results)} участках (включая аутсорсинг)")
    return results

def search_by_item(item_number: str):
    """
    Ищет конкретное изделие по его полному номеру во всех таблицах, включая аутсорсинг.
    Возвращает список: [(участок, qr_data, telegram_id, creation_date, modification_date)]
    """
    results = []
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # === 1. Поиск в обычных таблицах ===
    for table in tables:
        if table in ['users', 'user_creation_dates', 'аутсорсинг']:
            continue

        try:
            cursor.execute(f'''
                SELECT qr_data, telegram_id, creation_date, modification_date 
                FROM "{table}" 
                WHERE qr_data LIKE ?
            ''', (f'{item_number}%',))
            rows = cursor.fetchall()
            if rows:
                readable_workshop = table.replace("_", " ")
                for row in rows:
                    results.append((readable_workshop, row[0], row[1], row[2], row[3]))
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

    # === 2. Поиск в таблице "аутсорсинг" ===
    try:
        cursor.execute('''
            SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
            FROM "аутсорсинг"
            WHERE "артикул" = ?
        ''', (item_number,))
        row = cursor.fetchone()
        if row:
            артикул, аутсорсер, дата_заявки, дата_получения = row
            if дата_заявки and not дата_получения:
                results.append(("Аутсорсинг", артикул, аутсорсер, дата_заявки, None))
            elif дата_получения:
                results.append(("Упаковка", артикул, аутсорсер, дата_заявки, дата_получения))
    except sqlite3.Error as e:
        logger.error(f"Ошибка при запросе к таблице 'аутсорсинг': {e}")

    conn.close()
    logger.info(f"Поиск по изделию {item_number}: найдено {len(results)} записей (включая аутсорсинг)")
    return results

def search_packaged_items(order_number: str):
    """
    Ищет все изделия по номеру заказа, которые прошли через:
    - Участок упаковки
    - Аутсорсинг (если есть дата получения)
    Возвращает список: [(qr_data, telegram_id, creation_date, modification_date)]
    """
    results = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        pattern = f"{order_number}%"

        # 1. Участок упаковки
        cursor.execute(f'''
            SELECT qr_data, telegram_id, creation_date, modification_date 
            FROM "{PACKAGING_TABLE_NAME}" 
            WHERE qr_data LIKE ?
        ''', (pattern,))
        results.extend(cursor.fetchall())

        # 2. Аутсорсинг — если есть дата получения
        cursor.execute('''
            SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
            FROM "аутсорсинг"
            WHERE "артикул" LIKE ? AND "дата_получения" IS NOT NULL
        ''', (pattern,))
        rows = cursor.fetchall()
        for артикул, аутсорсер, дата_заявки, дата_получения in rows:
            results.append((артикул, аутсорсер, дата_заявки, дата_получения))

        conn.close()
        logger.info(f"Поиск упакованных изделий по заказу {order_number}: найдено {len(results)} записей (включая аутсорсинг)")
        return results
    except sqlite3.Error as e:
        logger.error(f"Ошибка при поиске упакованных изделий по заказу {order_number}: {e}")
        return []

# === Остальные функции без изменений ===
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
        
        cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, full_name) 
            VALUES (?, ?)
        ''', (telegram_id, full_name))
        
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
