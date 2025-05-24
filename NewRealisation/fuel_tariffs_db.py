import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional

class FuelTariffsDB:
    def __init__(self, db_path="fuel_tariffs.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица заправок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gas_stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                city TEXT,
                region TEXT,
                phone TEXT,
                email TEXT,
                working_hours TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица видов топлива
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fuel_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                octane_rating INTEGER,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица тарифов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fuel_tariffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL,
                fuel_type_id INTEGER NOT NULL,
                price_per_liter REAL NOT NULL,
                currency TEXT DEFAULT 'RUB',
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (station_id) REFERENCES gas_stations (id),
                FOREIGN KEY (fuel_type_id) REFERENCES fuel_types (id)
            )
        ''')
        
        # Таблица скидок и акций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER,
                fuel_type_id INTEGER,
                discount_type TEXT NOT NULL, -- 'percentage', 'fixed_amount', 'loyalty'
                discount_value REAL NOT NULL,
                min_liters REAL DEFAULT 0,
                description TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (station_id) REFERENCES gas_stations (id),
                FOREIGN KEY (fuel_type_id) REFERENCES fuel_types (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Заполняем базу тестовыми данными
        self.populate_test_data()
    
    def populate_test_data(self):
        """Заполнение базы тестовыми данными"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже данные
        cursor.execute("SELECT COUNT(*) FROM gas_stations")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return
        
        # Добавляем заправки
        stations = [
            ("Лукойл №1", "ул. Ленина, 15", "Саратов", "Саратовская область", "+7(8452)123-456", "lukoil1@example.com", "24/7"),
            ("Роснефть №5", "пр. Кирова, 42", "Саратов", "Саратовская область", "+7(8452)234-567", "rosneft5@example.com", "06:00-23:00"),
            ("Газпром №3", "ул. Московская, 78", "Саратов", "Саратовская область", "+7(8452)345-678", "gazprom3@example.com", "24/7"),
            ("Татнефть №2", "ул. Вольская, 123", "Саратов", "Саратовская область", "+7(8452)456-789", "tatneft2@example.com", "05:30-23:30")
        ]
        
        cursor.executemany('''
            INSERT INTO gas_stations (name, address, city, region, phone, email, working_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', stations)
        
        # Добавляем виды топлива
        fuel_types = [
            ("АИ-92", 92, "Бензин автомобильный неэтилированный"),
            ("АИ-95", 95, "Бензин автомобильный неэтилированный премиум"),
            ("АИ-98", 98, "Бензин автомобильный неэтилированный супер"),
            ("ДТ", None, "Дизельное топливо"),
            ("ДТ Евро-5", None, "Дизельное топливо экологического класса Евро-5"),
            ("Газ", None, "Сжиженный природный газ")
        ]
        
        cursor.executemany('''
            INSERT INTO fuel_types (name, octane_rating, description)
            VALUES (?, ?, ?)
        ''', fuel_types)
        
        # Добавляем тарифы
        tariffs = [
            # Лукойл №1
            (1, 1, 52.30),  # АИ-92
            (1, 2, 54.37),  # АИ-95
            (1, 3, 58.45),  # АИ-98
            (1, 4, 49.80),  # ДТ
            (1, 5, 51.20),  # ДТ Евро-5
            (1, 6, 28.50),  # Газ
            
            # Роснефть №5
            (2, 1, 52.10),  # АИ-92
            (2, 2, 54.15),  # АИ-95
            (2, 3, 58.20),  # АИ-98
            (2, 4, 49.60),  # ДТ
            (2, 5, 51.00),  # ДТ Евро-5
            (2, 6, 28.30),  # Газ
            
            # Газпром №3
            (3, 1, 52.50),  # АИ-92
            (3, 2, 54.60),  # АИ-95
            (3, 3, 58.70),  # АИ-98
            (3, 4, 50.00),  # ДТ
            (3, 5, 51.40),  # ДТ Евро-5
            (3, 6, 28.70),  # Газ
            
            # Татнефть №2
            (4, 1, 51.90),  # АИ-92
            (4, 2, 53.95),  # АИ-95
            (4, 3, 57.95),  # АИ-98
            (4, 4, 49.40),  # ДТ
            (4, 5, 50.80),  # ДТ Евро-5
            (4, 6, 28.10),  # Газ
        ]
        
        cursor.executemany('''
            INSERT INTO fuel_tariffs (station_id, fuel_type_id, price_per_liter)
            VALUES (?, ?, ?)
        ''', tariffs)
        
        # Добавляем скидки
        discounts = [
            (1, 1, 'percentage', 3.0, 20.0, 'Скидка 3% при заправке от 20 литров АИ-92'),
            (1, 2, 'percentage', 2.0, 15.0, 'Скидка 2% при заправке от 15 литров АИ-95'),
            (2, 4, 'fixed_amount', 1.5, 30.0, 'Скидка 1.5 руб/л при заправке ДТ от 30 литров'),
            (3, 6, 'percentage', 5.0, 10.0, 'Скидка 5% на газ при заправке от 10 литров'),
        ]
        
        cursor.executemany('''
            INSERT INTO discounts (station_id, fuel_type_id, discount_type, discount_value, min_liters, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', discounts)
        
        conn.commit()
        conn.close()
    
    def get_all_stations(self) -> List[Dict]:
        """Получить все заправки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, address, city, region, phone, email, working_hours
            FROM gas_stations
            ORDER BY name
        ''')
        
        stations = []
        for row in cursor.fetchall():
            stations.append({
                'id': row[0],
                'name': row[1],
                'address': row[2],
                'city': row[3],
                'region': row[4],
                'phone': row[5],
                'email': row[6],
                'working_hours': row[7]
            })
        
        conn.close()
        return stations
    
    def get_fuel_types(self) -> List[Dict]:
        """Получить все виды топлива"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, octane_rating, description
            FROM fuel_types
            ORDER BY name
        ''')
        
        fuel_types = []
        for row in cursor.fetchall():
            fuel_types.append({
                'id': row[0],
                'name': row[1],
                'octane_rating': row[2],
                'description': row[3]
            })
        
        conn.close()
        return fuel_types
    
    def get_station_tariffs(self, station_id: int) -> List[Dict]:
        """Получить тарифы для конкретной заправки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                ft.id as tariff_id,
                gs.name as station_name,
                fuel.name as fuel_name,
                fuel.octane_rating,
                ft.price_per_liter,
                ft.currency,
                ft.valid_from,
                ft.valid_until,
                ft.is_active
            FROM fuel_tariffs ft
            JOIN gas_stations gs ON ft.station_id = gs.id
            JOIN fuel_types fuel ON ft.fuel_type_id = fuel.id
            WHERE ft.station_id = ? AND ft.is_active = 1
            ORDER BY fuel.name
        ''', (station_id,))
        
        tariffs = []
        for row in cursor.fetchall():
            tariffs.append({
                'tariff_id': row[0],
                'station_name': row[1],
                'fuel_name': row[2],
                'octane_rating': row[3],
                'price_per_liter': row[4],
                'currency': row[5],
                'valid_from': row[6],
                'valid_until': row[7],
                'is_active': row[8]
            })
        
        conn.close()
        return tariffs
    
    def get_fuel_price(self, station_id: int, fuel_type_id: int) -> Optional[float]:
        """Получить цену топлива для конкретной заправки и вида топлива"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT price_per_liter
            FROM fuel_tariffs
            WHERE station_id = ? AND fuel_type_id = ? AND is_active = 1
            ORDER BY valid_from DESC
            LIMIT 1
        ''', (station_id, fuel_type_id))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_applicable_discounts(self, station_id: int, fuel_type_id: int, liters: float) -> List[Dict]:
        """Получить применимые скидки"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                id, discount_type, discount_value, min_liters, description
            FROM discounts
            WHERE (station_id = ? OR station_id IS NULL)
            AND (fuel_type_id = ? OR fuel_type_id IS NULL)
            AND min_liters <= ?
            AND is_active = 1
            AND (valid_until IS NULL OR valid_until > datetime('now'))
            ORDER BY discount_value DESC
        ''', (station_id, fuel_type_id, liters))
        
        discounts = []
        for row in cursor.fetchall():
            discounts.append({
                'id': row[0],
                'discount_type': row[1],
                'discount_value': row[2],
                'min_liters': row[3],
                'description': row[4]
            })
        
        conn.close()
        return discounts
    
    def calculate_price_with_discounts(self, station_id: int, fuel_type_id: int, liters: float) -> Dict:
        """Рассчитать цену с учетом скидок"""
        base_price = self.get_fuel_price(station_id, fuel_type_id)
        if not base_price:
            return {'error': 'Тариф не найден'}
        
        base_cost = base_price * liters
        discounts = self.get_applicable_discounts(station_id, fuel_type_id, liters)
        
        total_discount = 0
        applied_discounts = []
        
        for discount in discounts:
            if discount['discount_type'] == 'percentage':
                discount_amount = base_cost * (discount['discount_value'] / 100)
            elif discount['discount_type'] == 'fixed_amount':
                discount_amount = discount['discount_value'] * liters
            else:
                continue
            
            total_discount += discount_amount
            applied_discounts.append({
                'description': discount['description'],
                'amount': round(discount_amount, 2)
            })
        
        final_cost = max(0, base_cost - total_discount)
        
        return {
            'base_price_per_liter': base_price,
            'liters': liters,
            'base_cost': round(base_cost, 2),
            'total_discount': round(total_discount, 2),
            'final_cost': round(final_cost, 2),
            'final_price_per_liter': round(final_cost / liters, 2) if liters > 0 else 0,
            'applied_discounts': applied_discounts
        }
    
    def update_tariff(self, station_id: int, fuel_type_id: int, new_price: float):
        """Обновить тариф"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE fuel_tariffs
            SET price_per_liter = ?, updated_at = datetime('now')
            WHERE station_id = ? AND fuel_type_id = ? AND is_active = 1
        ''', (new_price, station_id, fuel_type_id))
        
        conn.commit()
        conn.close()
    
    def add_station(self, name: str, address: str, city: str, region: str, 
                   phone: str = None, email: str = None, working_hours: str = None) -> int:
        """Добавить новую заправку"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO gas_stations (name, address, city, region, phone, email, working_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, address, city, region, phone, email, working_hours))
        
        station_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return station_id
    
    def add_tariff(self, station_id: int, fuel_type_id: int, price_per_liter: float):
        """Добавить новый тариф"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO fuel_tariffs (station_id, fuel_type_id, price_per_liter)
            VALUES (?, ?, ?)
        ''', (station_id, fuel_type_id, price_per_liter))
        
        conn.commit()
        conn.close()

if __name__ == "__main__":
    # Тестирование
    db = FuelTariffsDB()
    
    print("=== Все заправки ===")
    stations = db.get_all_stations()
    for station in stations:
        print(f"{station['id']}: {station['name']} - {station['address']}")
    
    print("\n=== Виды топлива ===")
    fuel_types = db.get_fuel_types()
    for fuel in fuel_types:
        print(f"{fuel['id']}: {fuel['name']} ({fuel['octane_rating'] or 'N/A'})")
    
    print("\n=== Тарифы Лукойл №1 ===")
    tariffs = db.get_station_tariffs(1)
    for tariff in tariffs:
        print(f"{tariff['fuel_name']}: {tariff['price_per_liter']} {tariff['currency']}/л")
    
    print("\n=== Расчет стоимости 25 литров АИ-95 на Лукойл №1 ===")
    calculation = db.calculate_price_with_discounts(1, 2, 25.0)
    print(f"Базовая стоимость: {calculation['base_cost']} руб.")
    print(f"Скидка: {calculation['total_discount']} руб.")
    print(f"Итого: {calculation['final_cost']} руб.")
    if calculation['applied_discounts']:
        print("Применённые скидки:")
        for discount in calculation['applied_discounts']:
            print(f"  - {discount['description']}: -{discount['amount']} руб.")
