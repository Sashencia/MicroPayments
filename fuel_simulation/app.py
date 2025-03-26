from flask import Flask, render_template, jsonify
import grpc
import threading
import time
import sys
import os

# Добавляем путь к родительской директории (MicroPayments)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Теперь можно импортировать payment_pb2 и payment_pb2_grpc
import payment_pb2
import payment_pb2_grpc

#app = Flask(__name__)

import client
import bank_account
from client import FuelPumpSimulator
from bank_account import BankAccount
from client import process_fuel_payment
from flask import Flask, render_template, jsonify
import grpc
import threading
import time
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

class BankAccount:
    def __init__(self, user_id, initial_balance):
        self.user_id = user_id
        self.balance = round(float(initial_balance), 2)
        self.lock = threading.Lock()

    def get_balance(self):
        with self.lock:
            return self.balance

    def withdraw(self, amount):
        with self.lock:
            amount = round(float(amount), 2)
            if amount <= 0:
                return False
            if self.balance >= amount:
                self.balance -= amount
                return True
            return False

class RecipientAccount:
    def __init__(self, user_id, initial_balance):
        self.user_id = user_id
        self.balance = initial_balance

    def deposit(self, amount):
        self.balance += amount
        print(f"Recipient account: Deposited {amount} RUB. New balance: {self.balance} RUB")

    def get_balance(self):
        return self.balance

class HoldManager:
    def __init__(self):
        self.holds = []
        self.current_hold = None
        self.lock = threading.Lock()
    
    def create_hold(self, amount, timestamp):
        with self.lock:
            self.current_hold = {
                "amount": amount,
                "timestamp": timestamp,
                "remaining": amount,
                "status": "active"
            }
            self.holds.append(self.current_hold)
            return self.current_hold
    
    def update_hold(self, used_amount):
        with self.lock:
            if self.current_hold and self.current_hold["status"] == "active":
                self.current_hold["remaining"] -= used_amount
                if self.current_hold["remaining"] <= 0:
                    self.current_hold["status"] = "completed"
                return True
            return False
    
    def get_holds(self, limit=5):
        with self.lock:
            return self.holds[-limit:] if limit else self.holds

class OPKCMP:
    def __init__(self):
        self.buffer = []
        self.final_packet_received = False
        self.final_balance = 0.0

    def add_packet(self, packet):
        self.buffer.append(packet)
        logging.info(
            f"OPKCMP: Packet added - Time: {packet['time']}, "
            f"Liters: {packet['liters']:.3f}, "
            f"Balance: {packet['balance']:.2f}, "
            f"Final: {'Yes' if packet.get('is_final', False) else 'No'}"
        )

    def process_final_packet(self, total_cost):
        if self.buffer:
            self.final_packet_received = True
            self.final_balance = total_cost  # Используем total_cost вместо balance последнего пакета
            print(f"OPKCMP: Final packet processed. Total cost to recipient: {self.final_balance} RUB")

    def send_final_balance_to_recipient(self, recipient_account):
        if self.final_packet_received:
            recipient_account.deposit(self.final_balance)
            print(f"OPKCMP: Final balance {self.final_balance} RUB sent to recipient")
            self.buffer.clear()
            self.final_packet_received = False

class FuelPumpSimulator:
    def __init__(self, flow_rate_liters_per_second):
        self.flow_rate = flow_rate_liters_per_second
        self.total_fuel_dispensed = 0
        self.is_pumping = False

    def start_pumping(self):
        self.is_pumping = True
        print("Fuel pumping started.")

    def stop_pumping(self):
        self.is_pumping = False
        print("Fuel pumping stopped.")

    def get_fuel_consumed(self, time_interval):
        if self.is_pumping:
            fuel_consumed = self.flow_rate * time_interval
            self.total_fuel_dispensed += fuel_consumed
            return fuel_consumed
        return 0

def validate_payment_data(fuel_price, liters, balance):
    if fuel_price <= 0:
        raise ValueError("Fuel price must be positive")
    if liters < 0:
        raise ValueError("Liters cannot be negative")
    if balance < 0:
        raise ValueError("Balance cannot be negative")
    return True

def process_fuel_payment(stub, fuel_price_per_liter, liters, is_finished=False):
    try:
        validate_payment_data(fuel_price_per_liter, liters, bank_account.get_balance())
        
        start_time = time.time()
        response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
            fuel_price_per_liter=fuel_price_per_liter,
            liters=liters,
            is_finished=is_finished
        ))
        end_time = time.time()
        return response, end_time - start_time
    except ValueError as e:
        print(f"Validation error: {str(e)}")
        stop_fueling.set()
        return payment_pb2.FuelPaymentResponse(success=False), 0
    except grpc.RpcError as e:
        print(f"GRPC error: {e.code()}: {e.details()}")
        stop_fueling.set()
        return payment_pb2.FuelPaymentResponse(success=False), 0

app = Flask(__name__)

# Global variables
fueling_active = False
fuel_pump = None
stub = None
total_liters = 0.0
total_cost = 0.0
stop_fueling = threading.Event()
packet_log = []
real_time_data = {"liters": 0.0, "balance": 0.0}
opkcmp = OPKCMP()
recipient_account = RecipientAccount(user_id="recipient1", initial_balance=0.0)

def connect_to_grpc_server():
    global stub
    try:
        channel = grpc.insecure_channel('localhost:50051')
        # Проверяем соединение
        grpc.channel_ready_future(channel).result(timeout=5)
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        print("GRPC connection established successfully")
    except grpc.RpcError as e:
        print(f"GRPC connection failed: {e.code()}: {e.details()}")
        stub = None
    except Exception as e:
        print(f"GRPC connection error: {str(e)}")
        stub = None

def finalize_fueling():
    global total_liters, total_cost, packet_log, opkcmp, recipient_account
    
    # Фиксация финального состояния
    completion_packet = {
        "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "liters": 0,
        "balance": round(bank_account.get_balance(), 2),
        "is_final": True,
        "is_completion": True
    }
    
    packet_log.append(completion_packet)
    opkcmp.add_packet(completion_packet)
    
    # Обработка финального платежа
    opkcmp.process_final_packet(round(total_cost, 2))
    opkcmp.send_final_balance_to_recipient(recipient_account)
    
    # Финансовая финализация
    if stub:
        process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)

# Глобальные переменные
hold_manager = HoldManager()

def fueling_process(stub, fuel_price_per_liter, fuel_pump, bank_account):
    global total_liters, total_cost, stop_fueling, packet_log, real_time_data, opkcmp, recipient_account
    
    # Константы
    FRAME_INTERVAL = 0.1  # интервал между кадрами (сек)
    TARGET_PACKET_SIZE = 0.3  # размер пакета для отправки (литры)
    
    frame_buffer = []  # буфер для хранения кадров
    buffer_liters = 0  # накопленные литры в буфере
    
    while not stop_fueling.is_set():
        try:
            # Получаем текущее количество топлива
            fuel_consumed = fuel_pump.get_fuel_consumed(FRAME_INTERVAL)
            if fuel_consumed <= 0:
                time.sleep(FRAME_INTERVAL)
                continue
            
            # Обновляем баланс
            cost = fuel_price_per_liter * fuel_consumed
            if not bank_account.withdraw(cost):
                stop_fueling.set()
                break
            
            # Сохраняем кадр
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            frame = {
                "time": current_time,
                "liters": fuel_consumed,
                "balance": bank_account.get_balance()
            }
            frame_buffer.append(frame)
            
            # Обновляем общие показатели
            buffer_liters += fuel_consumed
            total_liters += fuel_consumed
            total_cost += cost
            
            # Обновляем данные реального времени
            real_time_data = {
                "liters": total_liters,
                "balance": bank_account.get_balance()
            }
            
            # Если накопили достаточно для пакета
            if buffer_liters >= TARGET_PACKET_SIZE:
                packet = {
                    "time": current_time,
                    "liters": buffer_liters,
                    "balance": bank_account.get_balance(),
                    "is_final": False,
                    "frames": frame_buffer.copy()  # сохраняем все кадры
                }
                
                packet_log.append(packet)
                opkcmp.add_packet(packet)
                
                # Отправка платежа
                response, _ = process_fuel_payment(stub, fuel_price_per_liter, buffer_liters)
                if not response.success:
                    stop_fueling.set()
                    break
                
                # Очищаем буферы
                buffer_liters = 0
                frame_buffer = []
            
            time.sleep(FRAME_INTERVAL)
            
        except Exception as e:
            logging.error(f"Fueling error: {str(e)}")
            stop_fueling.set()
            break

    # Обработка оставшегося топлива после остановки
    if buffer_liters > 0:
        final_packet = {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "liters": buffer_liters,
            "balance": bank_account.get_balance(),
            "is_final": True,
            "frames": frame_buffer
        }
        packet_log.append(final_packet)
        opkcmp.add_packet(final_packet)

    # Финализация
    finalize_fueling()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/toggle_fueling', methods=['POST'])
def toggle_fueling():
    global fueling_active, fuel_pump, stop_fueling, packet_log
    if not fueling_active:
        # Reset all counters when starting new fueling
        fueling_active = True
        stop_fueling.clear()
        packet_log = []
        global total_liters, total_cost
        total_liters = 0.0
        total_cost = 0.0
        fuel_pump.start_pumping()
        threading.Thread(target=fueling_process, args=(stub, fuel_price_per_liter, fuel_pump, bank_account)).start()
        return jsonify({"status": "started"})
    else:
        fueling_active = False
        stop_fueling.set()
        fuel_pump.stop_pumping()
        return jsonify({"status": "stopped"})

@app.route('/get_fuel_data', methods=['GET'])
def get_fuel_data():
    global total_liters, total_cost, bank_account, packet_log, real_time_data, opkcmp, recipient_account
    
    # Ensure the last packet is marked as final if fueling is stopped
    if not fueling_active and packet_log and not packet_log[-1].get('is_final', False):
        packet_log[-1]['is_final'] = True
        if opkcmp.buffer and not opkcmp.buffer[-1].get('is_final', False):
            opkcmp.buffer[-1]['is_final'] = True
    
    return jsonify({
        "total_liters": total_liters,
        "total_cost": total_cost,
        "balance": bank_account.get_balance(),
        "packet_log": packet_log[-10:],
        "real_time_data": real_time_data,
        "opkcmp_log": opkcmp.buffer[-10:],
        "recipient_balance": recipient_account.get_balance(),
        "fueling_active": fueling_active,  # Add fueling status to response
        "holds": hold_manager.get_holds(5),
        "current_hold": hold_manager.current_hold
    })

@app.route('/add_fuel', methods=['POST'])
def add_fuel():
    data = request.json
    print(f"Получен пакет: {data['liters']} л, баланс: {data['balance']} руб")
    return jsonify({"status": "ok"})

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Формат логов
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Логи в файл с ротацией
    file_handler = RotatingFileHandler(
        'fuel_system.log', 
        maxBytes=1024*1024, 
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Логи в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


if __name__ == '__main__':
    setup_logging()
    logging.info("Starting fuel system application")
    connect_to_grpc_server()
    fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)
    bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)
    fuel_price_per_liter = 54.37
    app.run(debug=True)