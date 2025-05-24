from fuel_tariffs_db import FuelTariffsDB
from Bank_Simulator import BankAccount
import time
from datetime import datetime
from typing import Dict, List, Optional
import logging

class EnhancedPaymentService:
    """
    Улучшенный сервис микроплатежей с интеграцией базы данных тарифов
    """
    
    def __init__(self, bank_simulator: BankAccount, db_path: str = "fuel_tariffs.db"):
        self.bank = bank_simulator
        self.tariffs_db = FuelTariffsDB(db_path)
        self.current_session = None
        self.transaction_buffer = []
        self.holds = []
        self.logger = self._setup_logger()
        
    def _setup_logger(self):
        """Настройка логирования"""
        logger = logging.getLogger('enhanced_payment_service')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def start_fueling_session(self, station_id: int, fuel_type_id: int, 
                            estimated_liters: float = 50.0) -> Dict:
        """
        Начать сессию заправки с автоматическим расчетом тарифов
        """
        try:
            # Получаем информацию о тарифе
            fuel_price = self.tariffs_db.get_fuel_price(station_id, fuel_type_id)
            if not fuel_price:
                return {
                    'success': False,
                    'error': 'Тариф для данной заправки и типа топлива не найден'
                }
            
            # Получаем информацию о заправке и топливе
            stations = self.tariffs_db.get_all_stations()
            station_info = next((s for s in stations if s['id'] == station_id), None)
            
            fuel_types = self.tariffs_db.get_fuel_types()
            fuel_info = next((f for f in fuel_types if f['id'] == fuel_type_id), None)
            
            if not station_info or not fuel_info:
                return {
                    'success': False,
                    'error': 'Информация о заправке или типе топлива не найдена'
                }
            
            # Рассчитываем предварительную стоимость с учетом скидок
            price_calculation = self.tariffs_db.calculate_price_with_discounts(
                station_id, fuel_type_id, estimated_liters
            )
            
            # Устанавливаем холд (с запасом 20%)
            estimated_cost = price_calculation['final_cost']
            hold_amount = estimated_cost * 1.2
            
            if not self.bank.hold(hold_amount):
                return {
                    'success': False,
                    'error': 'Недостаточно средств для установки холда'
                }
            
            # Создаем сессию
            self.current_session = {
                'session_id': f"session_{int(time.time())}",
                'station_id': station_id,
                'fuel_type_id': fuel_type_id,
                'station_name': station_info['name'],
                'fuel_name': fuel_info['name'],
                'base_price_per_liter': fuel_price,
                'estimated_liters': estimated_liters,
                'estimated_cost': estimated_cost,
                'hold_amount': hold_amount,
                'actual_liters': 0.0,
                'actual_cost': 0.0,
                'start_time': datetime.now(),
                'transactions': [],
                'applied_discounts': price_calculation.get('applied_discounts', [])
            }
            
            self.logger.info(
                f"Сессия заправки начата: {self.current_session['session_id']} "
                f"на {station_info['name']}, топливо: {fuel_info['name']}, "
                f"холд: {hold_amount:.2f} руб."
            )
            
            return {
                'success': True,
                'session': self.current_session,
                'price_info': price_calculation
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при начале сессии заправки: {str(e)}")
            return {
                'success': False,
                'error': f'Внутренняя ошибка: {str(e)}'
            }
    
    def process_fuel_transaction(self, liters: float) -> Dict:
        """
        Обработать транзакцию заправки
        """
        if not self.current_session:
            return {
                'success': False,
                'error': 'Активная сессия заправки не найдена'
            }
        
        try:
            # Рассчитываем стоимость с учетом текущих скидок
            total_liters = self.current_session['actual_liters'] + liters
            price_calculation = self.tariffs_db.calculate_price_with_discounts(
                self.current_session['station_id'],
                self.current_session['fuel_type_id'],
                total_liters
            )
            
            # Стоимость только за новые литры
            previous_cost = self.current_session['actual_cost']
            new_total_cost = price_calculation['final_cost']
            transaction_cost = new_total_cost - previous_cost
            
            # Проверяем, достаточно ли холда
            if self.bank.hold_amount < transaction_cost:
                # Устанавливаем дополнительный холд
                additional_hold = max(transaction_cost * 2, 100.0)
                if not self.bank.hold(additional_hold):
                    return {
                        'success': False,
                        'error': 'Недостаточно средств для продолжения заправки'
                    }
                self.current_session['hold_amount'] += additional_hold
                self.logger.info(f"Установлен дополнительный холд: {additional_hold:.2f} руб.")
            
            # Списываем средства
            if not self.bank.charge(transaction_cost):
                return {
                    'success': False,
                    'error': 'Ошибка при списании средств'
                }
            
            # Обновляем сессию
            transaction = {
                'timestamp': datetime.now(),
                'liters': liters,
                'cost': transaction_cost,
                'total_liters': total_liters,
                'total_cost': new_total_cost
            }
            
            self.current_session['actual_liters'] = total_liters
            self.current_session['actual_cost'] = new_total_cost
            self.current_session['transactions'].append(transaction)
            
            # Добавляем в буфер транзакций
            self.transaction_buffer.append({
                'session_id': self.current_session['session_id'],
                'transaction': transaction,
                'price_calculation': price_calculation
            })
            
            self.logger.info(
                f"Транзакция обработана: {liters:.3f}л, "
                f"стоимость: {transaction_cost:.2f} руб., "
                f"всего: {total_liters:.3f}л / {new_total_cost:.2f} руб."
            )
            
            return {
                'success': True,
                'transaction': transaction,
                'session_total': {
                    'liters': total_liters,
                    'cost': new_total_cost
                },
                'price_info': price_calculation
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при обработке транзакции: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка обработки транзакции: {str(e)}'
            }
    
    def finish_fueling_session(self) -> Dict:
        """
        Завершить сессию заправки
        """
        if not self.current_session:
            return {
                'success': False,
                'error': 'Активная сессия заправки не найдена'
            }
        
        try:
            # Освобождаем оставшийся холд
            self.bank.release_hold()
            
            # Финальный расчет с учетом всех скидок
            final_calculation = self.tariffs_db.calculate_price_with_discounts(
                self.current_session['station_id'],
                self.current_session['fuel_type_id'],
                self.current_session['actual_liters']
            )
            
            # Сохраняем итоговую информацию
            session_summary = {
                'session_id': self.current_session['session_id'],
                'station_name': self.current_session['station_name'],
                'fuel_name': self.current_session['fuel_name'],
                'start_time': self.current_session['start_time'],
                'end_time': datetime.now(),
                'total_liters': self.current_session['actual_liters'],
                'total_cost': self.current_session['actual_cost'],
                'base_price_per_liter': self.current_session['base_price_per_liter'],
                'final_price_per_liter': final_calculation['final_price_per_liter'],
                'total_discount': final_calculation['total_discount'],
                'applied_discounts': final_calculation['applied_discounts'],
                'transactions_count': len(self.current_session['transactions']),
                'hold_amount': self.current_session['hold_amount']
            }
            
            self.logger.info(
                f"Сессия заправки завершена: {session_summary['session_id']}, "
                f"итого: {session_summary['total_liters']:.3f}л / "
                f"{session_summary['total_cost']:.2f} руб."
            )
            
            # Очищаем текущую сессию
            self.current_session = None
            
            return {
                'success': True,
                'session_summary': session_summary
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при завершении сессии: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка завершения сессии: {str(e)}'
            }
    
    def get_available_stations(self) -> List[Dict]:
        """Получить список доступных заправок"""
        return self.tariffs_db.get_all_stations()
    
    def get_station_tariffs(self, station_id: int) -> List[Dict]:
        """Получить тарифы для заправки"""
        return self.tariffs_db.get_station_tariffs(station_id)
    
    def get_fuel_types(self) -> List[Dict]:
        """Получить список типов топлива"""
        return self.tariffs_db.get_fuel_types()
    
    def calculate_estimated_cost(self, station_id: int, fuel_type_id: int, 
                               liters: float) -> Dict:
        """Рассчитать предварительную стоимость заправки"""
        return self.tariffs_db.calculate_price_with_discounts(
            station_id, fuel_type_id, liters
        )
    
    def get_current_session_info(self) -> Optional[Dict]:
        """Получить информацию о текущей сессии"""
        return self.current_session
    
    def get_transaction_buffer(self, limit: int = 10) -> List[Dict]:
        """Получить буфер транзакций"""
        return self.transaction_buffer[-limit:] if limit else self.transaction_buffer
    
    def clear_transaction_buffer(self):
        """Очистить буфер транзакций"""
        self.transaction_buffer.clear()
        self.logger.info("Буфер транзакций очищен")

# Пример использования
if __name__ == "__main__":
    # Создаем банковский симулятор
    bank = BankAccount(1000000)
    
    # Создаем сервис микроплатежей
    payment_service = EnhancedPaymentService(bank)
    
    print("=== Доступные заправки ===")
    stations = payment_service.get_available_stations()
    for station in stations:
        print(f"{station['id']}: {station['name']} - {station['address']}")
    
    print("\n=== Тарифы Лукойл №1 ===")
    tariffs = payment_service.get_station_tariffs(1)
    for tariff in tariffs:
        print(f"{tariff['fuel_name']}: {tariff['price_per_liter']} руб./л")
    
    print("\n=== Расчет стоимости 30 литров АИ-95 ===")
    cost_estimate = payment_service.calculate_estimated_cost(1, 2, 30.0)
    print(f"Базовая стоимость: {cost_estimate['base_cost']} руб.")
    print(f"Скидка: {cost_estimate['total_discount']} руб.")
    print(f"Итого: {cost_estimate['final_cost']} руб.")
    
    print("\n=== Симуляция заправки ===")
    # Начинаем сессию
    session_result = payment_service.start_fueling_session(1, 2, 30.0)
    if session_result['success']:
        print(f"Сессия начата: {session_result['session']['session_id']}")
        print(f"Холд установлен: {session_result['session']['hold_amount']:.2f} руб.")
        
        # Симулируем несколько транзакций
        for i, liters in enumerate([5.0, 8.0, 12.0, 5.0], 1):
            print(f"\nТранзакция {i}: {liters} литров")
            transaction_result = payment_service.process_fuel_transaction(liters)
            if transaction_result['success']:
                total = transaction_result['session_total']
                print(f"  Стоимость транзакции: {transaction_result['transaction']['cost']:.2f} руб.")
                print(f"  Всего заправлено: {total['liters']:.1f}л / {total['cost']:.2f} руб.")
            else:
                print(f"  Ошибка: {transaction_result['error']}")
                break
        
        # Завершаем сессию
        print("\n=== Завершение сессии ===")
        finish_result = payment_service.finish_fueling_session()
        if finish_result['success']:
            summary = finish_result['session_summary']
            print(f"Сессия завершена: {summary['session_id']}")
            print(f"Итого заправлено: {summary['total_liters']:.3f} литров")
            print(f"Итого к оплате: {summary['total_cost']:.2f} руб.")
            print(f"Цена за литр: {summary['final_price_per_liter']:.2f} руб./л")
            if summary['applied_discounts']:
                print("Применённые скидки:")
                for discount in summary['applied_discounts']:
                    print(f"  - {discount['description']}: -{discount['amount']:.2f} руб.")
        else:
            print(f"Ошибка завершения: {finish_result['error']}")
    else:
        print(f"Ошибка начала сессии: {session_result['error']}")
    
    print(f"\nОстаток на счете: {bank.get_balance():.2f} руб.")
