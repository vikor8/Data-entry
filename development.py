# -*- coding: utf-8 -*-
"""
Файл development.py
Содержит вспомогательные функции для бота.
"""

import logging
import sqlite3
from datetime import datetime

from database import DB_PATH

logger = logging.getLogger(__name__)

def get_future_orders():
    """
    Возвращает заказы из таблицы Orders_KB, у которых:
    - Дата отгрузки >= сегодня (в формате DD.MM.YYYY)
    - Номер заказа НЕ начинается на 'VP' или 'BN'
    Сортирует по дате отгрузки в порядке ВОЗРАСТАНИЯ (ближайшие — сверху)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = datetime.now().date()
    logger.info(f"🔍 Фильтруем по дате: {today}")

    try:
        cursor.execute('''
            SELECT OrderNumber, Customer, City, ShippingDate
            FROM Orders_KB
            WHERE ShippingDate IS NOT NULL
              AND OrderNumber NOT LIKE 'VP%'
              AND OrderNumber NOT LIKE 'BN%'
        ''')

        all_rows = cursor.fetchall()
        logger.info(f"📥 Получено {len(all_rows)} строк до фильтрации.")

        # 🔥 Фильтруем вручную, чтобы корректно сравнить даты в формате DD.MM.YYYY
        filtered_rows = []
        for row in all_rows:
            try:
                date_str = row[3]
                # Парсим дату в формате DD.MM.YYYY
                shipping_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                if shipping_date >= today:
                    filtered_rows.append((row[0], row[1], row[2], date_str))
            except ValueError:
                logger.warning(f"⚠️ Некорректная дата в строке: {row}")

        # 🔥 Сортируем вручную по дате (DD.MM.YYYY)
        filtered_rows.sort(key=lambda x: datetime.strptime(x[3], "%d.%m.%Y"))

        logger.info(f"✅ Найдено {len(filtered_rows)} будущих заказов (без VP и BN)")

        for i, row in enumerate(filtered_rows[:5]):
            logger.info(f"  → {row}")

        conn.close()
        return filtered_rows

    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при запросе к таблице Orders_KB: {e}")
        return []
