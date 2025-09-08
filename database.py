# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных для BSG Аналитик бота (обновлён с поддержкой типов изделий)
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

# === Функции для работы с типами изделий ===

def get_type_id_by_suffix(suffix: str) -> int:
    """
    Возвращает ID типа изделия по суффиксу (без учёта регистра)
    z -> закладная (2)
    r -> рекламация (3)
    остальное -> изделие (1)
    """
    suffix = suffix.lower().strip()
    if suffix == 'z':
        return 2  # закладная
    elif suffix == 'r':
        return 3  # рекламация
    else:
        return 1  # изделие

def strip_suffix(item_number: str) -> tuple:
    """
    Удаляет суффикс z/r из номера изделия.
    Возвращает (базовый_номер, суффикс)
    """
    if not item_number:
        return item_number, ''
    if item_number[-1:].lower() in ['z', 'r']:
        return item_number[:-1], item_number[-1]
    return item_number, ''

# === Основные функции поиска ===

def get_table_names():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        all_tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        excluded = {'users', 'user_creation_dates', 'аутсорсинг', 'тип_изделия', 'sqlite_sequence'}
        return [t for t in all_tables if t not in excluded]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка таблиц: {e}")
        return []

def search_by_order(order_number: str):
    """
    Ищет все изделия по номеру заказа.
    Если ввод заканчивается на 'z' или 'r' — фильтрует по типу.
    В БД хранится номер без суффикса.
    """
    base_order, suffix = strip_suffix(order_number)
    if not base_order:
        logger.warning("Пустой номер заказа после удаления суффикса")
        return defaultdict(list)

    type_id = get_type_id_by_suffix(suffix) if suffix else None

    results = defaultdict(list)
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    pattern = f"{base_order}%"

    # Поиск в таблицах участков
    for table in tables:
        if table in ['users', 'user_creation_dates', 'аутсорсинг', 'тип_изделия']:
            continue

        try:
            if type_id is None:
                cursor.execute(f'''
                    SELECT qr_data, telegram_id, creation_date, modification_date 
                    FROM "{table}" 
                    WHERE qr_data LIKE ?
                ''', (pattern,))
            else:
                cursor.execute(f'''
                    SELECT qr_data, telegram_id, creation_date, modification_date 
                    FROM "{table}" 
                    WHERE qr_data LIKE ? AND тип_изделия_id = ?
                ''', (pattern, type_id))
            rows = cursor.fetchall()
            if rows:
                readable_workshop = table.replace("_", " ")
                results[readable_workshop].extend(rows)
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

    # Поиск в таблице "аутсорсинг"
    try:
        if type_id is None or type_id == 1:  # Только для "изделие" или всех
            cursor.execute('''
                SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
                FROM "аутсорсинг"
                WHERE "артикул" LIKE ?
            ''', (pattern,))
            rows = cursor.fetchall()
            for артикул, аутсорсер, дата_заявки, дата_получения in rows:
                if дата_заявки and not дата_получения:
                    results["Аутсорсинг"].append((артикул, аутсорсер, дата_заявки, None))
    except sqlite3.Error as e:
        logger.error(f"Ошибка при запросе к таблице 'аутсорсинг': {e}")

    conn.close()
    logger.info(f"Поиск по заказу {order_number} (база: {base_order}, тип: {type_id}): найдено в {len(results)} участках")
    return results

def search_by_item(item_number: str):
    """
    Ищет конкретное изделие по его номеру.
    Суффикс z/r не сохраняется в БД, используется только для определения типа.
    """
    if not item_number:
        return []

    base_item, suffix = strip_suffix(item_number)
    type_id = get_type_id_by_suffix(suffix)

    results = []
    tables = get_table_names()
    if not tables:
        logger.warning("Список таблиц пуст или ошибка подключения к БД.")
        return results

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table in tables:
        if table in ['users', 'user_creation_dates', 'аутсорсинг', 'тип_изделия']:
            continue

        try:
            cursor.execute(f'''
                SELECT qr_data, telegram_id, creation_date, modification_date 
                FROM "{table}" 
                WHERE qr_data = ? AND тип_изделия_id = ?
            ''', (base_item, type_id))
            rows = cursor.fetchall()
            if rows:
                readable_workshop = table.replace("_", " ")
                for row in rows:
                    results.append((readable_workshop, row[0], row[1], row[2], row[3]))
        except sqlite3.Error as e:
            logger.error(f"Ошибка при запросе к таблице '{table}': {e}")

    # Поиск в аутсорсинге (по артикулу без суффикса)
    try:
        cursor.execute('''
            SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
            FROM "аутсорсинг"
            WHERE "артикул" = ?
        ''', (base_item,))
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
    logger.info(f"Поиск по изделию {item_number} (база: {base_item}, тип: {type_id}): найдено {len(results)} записей")
    return results

def search_packaged_items(order_number: str):
    """
    Ищет все изделия по номеру заказа, которые прошли через:
    - Участок упаковки
    - Аутсорсинг (если есть дата получения)
    Возвращает список: [(qr_data, telegram_id, creation_date, modification_date)]
    """
    base_order, _ = strip_suffix(order_number)
    if not base_order:
        return []

    results = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        pattern = f"{base_order}%"

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

# === Остальные функции ===

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
