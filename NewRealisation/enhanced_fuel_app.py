from flask import Flask, render_template, jsonify, request
from enhanced_payment_service import EnhancedPaymentService
from Bank_Simulator import BankAccount
import threading
import time
import logging
from datetime import datetime

app = Flask(__name__)

# Глобальные переменные
bank_simulator = BankAccount(1000000)
payment_service = EnhancedPaymentService(bank_simulator)
fueling_active = False
stop_fueling = threading.Event()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def simulate_fueling_process(station_id, fuel_type_id, target_liters):
    """Симуляция процесса заправки"""
    global fueling_active
    
    try:
        # Начинаем сессию заправки
        session_result = payment_service.start_fueling_session(
            station_id, fuel_type_id, target_liters
        )
        
        if not session_result['success']:
            logger.error(f"Ошибка начала сессии: {session_result['error']}")
            fueling_active = False
            return
        
        logger.info(f"Сессия заправки начата: {session_result['session']['session_id']}")
        
        # Симулируем заправку небольшими порциями
        total_dispensed = 0.0
        flow_rate = 6.0  # литров в секунду
        update_interval = 0.1  # обновление каждые 100мс
        liters_per_update = flow_rate * update_interval
        
        while total_dispensed < target_liters and not stop_fueling.is_set():
            remaining = target_liters - total_dispensed
            current_portion = min(liters_per_update, remaining)
            
            # Обрабатываем транзакцию
            transaction_result = payment_service.process_fuel_transaction(current_portion)
            
            if not transaction_result['success']:
                logger.error(f"Ошибка транзакции: {transaction_result['error']}")
                break
            
            total_dispensed += current_portion
            time.sleep(update_interval)
        
        # Завершаем сессию
        finish_result = payment_service.finish_fueling_session()
        if finish_result['success']:
            logger.info(f"Сессия завершена. Заправлено: {total_dispensed:.3f} литров")
        else:
            logger.error(f"Ошибка завершения сессии: {finish_result['error']}")
            
    except Exception as e:
        logger.error(f"Ошибка в процессе заправки: {str(e)}")
    finally:
        fueling_active = False

@app.route('/')
def index():
    return render_template('enhanced_fuel_interface.html')

@app.route('/api/stations', methods=['GET'])
def get_stations():
    """Получить список заправок"""
    try:
        stations = payment_service.get_available_stations()
        return jsonify({
            'success': True,
            'stations': stations
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/fuel_types', methods=['GET'])
def get_fuel_types():
    """Получить список типов топлива"""
    try:
        fuel_types = payment_service.get_fuel_types()
        return jsonify({
            'success': True,
            'fuel_types': fuel_types
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/station_tariffs/<int:station_id>', methods=['GET'])
def get_station_tariffs(station_id):
    """Получить тарифы для заправки"""
    try:
        tariffs = payment_service.get_station_tariffs(station_id)
        return jsonify({
            'success': True,
            'tariffs': tariffs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/calculate_cost', methods=['POST'])
def calculate_cost():
    """Рассчитать стоимость заправки"""
    try:
        data = request.json
        station_id = data.get('station_id')
        fuel_type_id = data.get('fuel_type_id')
        liters = data.get('liters')
        
        if not all([station_id, fuel_type_id, liters]):
            return jsonify({
                'success': False,
                'error': 'Не все параметры указаны'
            })
        
        calculation = payment_service.calculate_estimated_cost(
            station_id, fuel_type_id, float(liters)
        )
        
        return jsonify({
            'success': True,
            'calculation': calculation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/start_fueling', methods=['POST'])
def start_fueling():
    """Начать заправку"""
    global fueling_active, stop_fueling
    
    try:
        if fueling_active:
            return jsonify({
                'success': False,
                'error': 'Заправка уже активна'
            })
        
        data = request.json
        station_id = data.get('station_id')
        fuel_type_id = data.get('fuel_type_id')
        target_liters = data.get('target_liters', 30.0)
        
        if not all([station_id, fuel_type_id]):
            return jsonify({
                'success': False,
                'error': 'Не все параметры указаны'
            })
        
        fueling_active = True
        stop_fueling.clear()
        
        # Запускаем процесс заправки в отдельном потоке
        threading.Thread(
            target=simulate_fueling_process,
            args=(int(station_id), int(fuel_type_id), float(target_liters))
        ).start()
        
        return jsonify({
            'success': True,
            'message': 'Заправка начата'
        })
        
    except Exception as e:
        fueling_active = False
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/stop_fueling', methods=['POST'])
def stop_fueling_endpoint():
    """Остановить заправку"""
    global fueling_active, stop_fueling
    
    try:
        if not fueling_active:
            return jsonify({
                'success': False,
                'error': 'Заправка не активна'
            })
        
        stop_fueling.set()
        fueling_active = False
        
        # Завершаем текущую сессию если она есть
        if payment_service.get_current_session_info():
            payment_service.finish_fueling_session()
        
        return jsonify({
            'success': True,
            'message': 'Заправка остановлена'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/status', methods=['GET'])
def get_status():
    """Получить текущий статус системы"""
    try:
        current_session = payment_service.get_current_session_info()
        transaction_buffer = payment_service.get_transaction_buffer(10)
        
        return jsonify({
            'success': True,
            'status': {
                'fueling_active': fueling_active,
                'bank_balance': round(bank_simulator.get_balance(), 2),
                'hold_amount': round(bank_simulator.hold_amount, 2),
                'current_session': current_session,
                'recent_transactions': transaction_buffer
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/update_tariff', methods=['POST'])
def update_tariff():
    """Обновить тариф"""
    try:
        data = request.json
        station_id = data.get('station_id')
        fuel_type_id = data.get('fuel_type_id')
        new_price = data.get('new_price')
        
        if not all([station_id, fuel_type_id, new_price]):
            return jsonify({
                'success': False,
                'error': 'Не все параметры указаны'
            })
        
        payment_service.tariffs_db.update_tariff(
            int(station_id), int(fuel_type_id), float(new_price)
        )
        
        return jsonify({
            'success': True,
            'message': 'Тариф обновлен'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/add_station', methods=['POST'])
def add_station():
    """Добавить новую заправку"""
    try:
        data = request.json
        name = data.get('name')
        address = data.get('address')
        city = data.get('city')
        region = data.get('region')
        phone = data.get('phone')
        email = data.get('email')
        working_hours = data.get('working_hours')
        
        if not all([name, address, city, region]):
            return jsonify({
                'success': False,
                'error': 'Не все обязательные поля заполнены'
            })
        
        station_id = payment_service.tariffs_db.add_station(
            name, address, city, region, phone, email, working_hours
        )
        
        return jsonify({
            'success': True,
            'station_id': station_id,
            'message': 'Заправка добавлена'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
