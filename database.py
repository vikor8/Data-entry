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

# === Вспомогательная функция для безопасного извлечения даты ===
def safe_date(date_str):
    """Безопасно извлекает дату из строки. Возвращает '-' при None или пустоте."""
    if not date_str or not str(date_str).strip():
        return "-"
    try:
        # Просто возвращаем строку, как в боте
        return str(date_str).strip() # Убираем split()[0], чтобы сохранить время, если нужно
    except:
        return "-"

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
                # Добавляем имя таблицы к каждому результату для ясности
                for row in rows:
                    results[readable_workshop].append((readable_workshop,) + row)
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
                # Проверяем, что изделие в аутсорсинге, но еще не получено
                if дата_заявки and not дата_получения:
                    results["Аутсорсинг"].append(("Аутсорсинг", артикул, аутсорсер, дата_заявки, None))
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
                # В аутсорсинге, но не получено
                results.append(("Аутсорсинг", артикул, аутсорсер, дата_заявки, None))
            elif дата_получения:
                # Получено из аутсорсинга, считаем "упакованным"
                results.append(("Упаковка (аутсорсинг)", артикул, аутсорсер, дата_заявки, дата_получения))
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
    Возвращает список: [(qr_data, fio, creation_date, modification_date)]
    """
    base_order, _ = strip_suffix(order_number)
    if not base_order:
        return []

    results = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        pattern = f"{base_order}%"

        # 1. Участок упаковки — добавляем telegram_id и получаем ФИО
        cursor.execute(f'''
            SELECT qr_data, telegram_id, creation_date, modification_date 
            FROM "{PACKAGING_TABLE_NAME}" 
            WHERE qr_data LIKE ?
        ''', (pattern,))
        rows = cursor.fetchall()
        for row in rows:
            qr_data, tid, created, modified = row
            # Получаем ФИО по telegram_id
            if tid is not None and tid != 0:
                fio = get_user_full_name(tid)
            else:
                fio = "-"
            # Для упаковки дата - это дата создания (запуска)
            results.append((qr_data, fio, created, modified))

        # 2. Аутсорсинг — если есть дата получения
        cursor.execute('''
            SELECT "артикул", "аутсорсер", "дата_заявки", "дата_получения"
            FROM "аутсорсинг"
            WHERE "артикул" LIKE ? AND "дата_получения" IS NOT NULL
        ''', (pattern,))
        rows = cursor.fetchall()
        for артикул, аутсорсер, дата_заявки, дата_получения in rows:
            if аутсорсер is not None and аутсорсер != 0:
                fio = get_user_full_name(аутсорсер)
            else:
                fio = "-"
            # Для аутсорсинга дата - это дата получения
            results.append((артикул, fio, дата_заявки, дата_получения))

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
    """Получает ФИО пользователя по telegram_id."""
    # Добавлена явная проверка на None и 0
    if telegram_id is None or telegram_id == 0:
        return "Неизвестно"

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT full_name FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "Неизвестно"
    except Exception as e:
        logger.error(f"Ошибка в get_user_full_name для ID {telegram_id}: {e}")
        return "Неизвестно"

def get_last_workshop_for_item(item_number: str):
    """
    Возвращает последний (по дате) участок, где было изделие.
    Использует только таблицы, кроме "Участок_упаковки".
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        tables = get_table_names()
        results = []

        for table in tables:
            # Исключаем упаковку из поиска "последнего участка"
            if table == PACKAGING_TABLE_NAME:
                continue
            try:
                cursor.execute(f'''
                    SELECT qr_data, telegram_id, creation_date, modification_date
                    FROM "{table}"
                    WHERE qr_data = ?
                ''', (item_number,))
                rows = cursor.fetchall()
                for qr, tid, created, modified in rows:
                    # Определяем дату: сначала modification, потом creation
                    date = modified if modified else created
                    if not date or not str(date).strip():
                        continue # Пропускаем записи без даты
                    # Добавляем в результаты: (таблица, telegram_id, дата)
                    results.append((table, tid, date))
            except sqlite3.Error as e:
                logger.error(f"Ошибка при поиске в таблице '{table}': {e}")

        conn.close()

        if not results:
            return None

        # Сортируем по дате (самая поздняя дата будет первой)
        # Предполагаем, что дата в формате, который можно сравнить строково (ISO)
        try:
            results.sort(key=lambda x: x[2], reverse=True)
        except Exception as sort_error:
            logger.error(f"Ошибка сортировки результатов по дате: {sort_error}")
            # Если сортировка не удалась, возвращаем первый найденный
            pass

        workshop, tid, date = results[0]
        full_name = get_user_full_name(tid)
        readable_workshop = workshop.replace("_", " ")
        return (readable_workshop, full_name, safe_date(date))

    except Exception as e:
        logger.error(f"Ошибка в get_last_workshop_for_item({item_number}): {e}")
        return None
