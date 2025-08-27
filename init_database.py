import sqlite3
import os

# Путь к базе данных
DB_PATH = "/srv/dev-disk-by-uuid-6cbacaea-af88-4ced-8990-f4f163606aae/home/bot/workshop_data_1.db"

# Список участков
WORKSHOPS = [
    "Участок раскроя",
    "Участок кормления",
    "Участок пресса",
    "Участок ЧПУ",
    "Участок рекламы",
    "Участок сборки",
    "Участок покраски",
    "Участок металла",
    "Участок порошковой покраски",
    "Участок стекла",
    "Участок упаковки"
]

def create_database():
    """Создает базу данных с пустыми таблицами"""
    
    # Создаем директорию, если она не существует
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"Создана директория: {db_dir}")
    
    # Подключаемся к базе данных
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Создание таблиц...")
    
    # Создаем таблицу пользователей (telegram_id как PRIMARY KEY)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL
        )
    ''')
    print("✓ Таблица 'users' создана")
    
    # Создаем таблицу для хранения дат создания пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_creation_dates (
            telegram_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
        )
    ''')
    print("✓ Таблица 'user_creation_dates' создана")
    
    # Создаем таблицу для каждого участка
    for workshop in WORKSHOPS:
        table_name = workshop.replace(" ", "_").replace("-", "_")
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qr_data TEXT NOT NULL,
                creation_date TEXT NOT NULL,
                modification_date TEXT,
                telegram_id INTEGER,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
            )
        ''')
        print(f"✓ Таблица '{table_name}' создана")
    
    # Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()
    
    print(f"\nБаза данных успешно создана: {DB_PATH}")

def show_database_structure():
    """Показывает структуру созданной базы данных"""
    
    if not os.path.exists(DB_PATH):
        print("База данных не найдена!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print("\nСтруктура базы данных:")
    print("=" * 50)
    
    for table in tables:
        table_name = table[0]
        if table_name != 'sqlite_sequence':  # Пропускаем служебную таблицу
            cursor.execute(f"PRAGMA table_info('{table_name}')")
            columns = cursor.fetchall()
            
            print(f"\nТаблица: {table_name}")
            print("-" * 30)
            for column in columns:
                constraints = ""
                if column[5] == 1:  # PRIMARY KEY
                    constraints += " PRIMARY KEY"
                if column[3] == 1:  # NOT NULL
                    constraints += " NOT NULL"
                if "REFERENCES" in str(column[4] or ""):  # FOREIGN KEY
                    constraints += f" {column[4]}"
                print(f"  {column[1]} ({column[2]}){constraints}")
    
    conn.close()

def clear_database():
    """Очищает все данные из таблиц (оставляет структуру)"""
    
    if not os.path.exists(DB_PATH):
        print("База данных не найдена!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Очищаем все таблицы
    for table in tables:
        table_name = table[0]
        if table_name != 'sqlite_sequence' and table_name != 'sqlite_master':  # Пропускаем служебные таблицы
            try:
                cursor.execute(f'DELETE FROM "{table_name}"')
                print(f"Очищена таблица: {table_name}")
            except Exception as e:
                print(f"Ошибка при очистке таблицы {table_name}: {e}")
    
    conn.commit()
    conn.close()
    print("Все таблицы очищены!")

def drop_database():
    """Удаляет все таблицы из базы данных"""
    
    if not os.path.exists(DB_PATH):
        print("База данных не найдена!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Удаляем все таблицы
    for table in tables:
        table_name = table[0]
        if table_name != 'sqlite_sequence' and table_name != 'sqlite_master':
            try:
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                print(f"Удалена таблица: {table_name}")
            except Exception as e:
                print(f"Ошибка при удалении таблицы {table_name}: {e}")
    
    conn.commit()
    conn.close()
    print("Все таблицы удалены!")

def test_database():
    """Тестовое заполнение базы данных"""
    
    if not os.path.exists(DB_PATH):
        print("База данных не найдена!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Добавляем тестового пользователя
        cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, full_name) 
            VALUES (?, ?)
        ''', (123456789, "Тестовый Пользователь"))
        
        cursor.execute('''
            INSERT OR IGNORE INTO user_creation_dates (telegram_id, created_at) 
            VALUES (?, ?)
        ''', (123456789, "2024-01-01 12:00:00"))
        
        # Добавляем тестовые данные в один из участков
        table_name = WORKSHOPS[0].replace(" ", "_").replace("-", "_")
        cursor.execute(f'''
            INSERT OR IGNORE INTO "{table_name}" 
            (qr_data, creation_date, telegram_id) 
            VALUES (?, ?, ?)
        ''', ("TEST_QR_001", "2024-01-01 12:00:00", 123456789))
        
        conn.commit()
        print("Тестовые данные добавлены успешно!")
        
        # Проверяем данные
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        print(f"Пользователи: {users}")
        
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("Управление базой данных для Telegram бота")
    print("=" * 50)
    
    while True:
        print("\nВыберите действие:")
        print("1. Создать базу данных с пустыми таблицами")
        print("2. Показать структуру базы данных")
        print("3. Очистить все данные из таблиц")
        print("4. Удалить все таблицы")
        print("5. Добавить тестовые данные")
        print("6. Выйти")
        
        choice = input("\nВведите номер действия (1-6): ").strip()
        
        if choice == "1":
            # Сначала удаляем старые таблицы, если они есть
            drop_database()
            create_database()
        elif choice == "2":
            show_database_structure()
        elif choice == "3":
            confirm = input("Вы уверены, что хотите очистить все данные? (y/N): ").strip().lower()
            if confirm == "y" or confirm == "yes":
                clear_database()
            else:
                print("Очистка отменена")
        elif choice == "4":
            confirm = input("Вы уверены, что хотите удалить все таблицы? (y/N): ").strip().lower()
            if confirm == "y" or confirm == "yes":
                drop_database()
            else:
                print("Удаление отменено")
        elif choice == "5":
            test_database()
        elif choice == "6":
            print("Выход...")
            break
        else:
            print("Неверный выбор. Попробуйте снова.")
