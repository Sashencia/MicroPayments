from flask import Flask, render_template, jsonify, request
import grpc
import threading
import time
import sys
import os
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# Настройка путей
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import payment_pb2
import payment_pb2_grpc

app = Flask(__name__)

# Классы
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
            hold = {
                "id": len(self.holds) + 1,
                "amount": round(amount, 2),
                "timestamp": timestamp,
                "remaining": round(amount, 2),
                "status": "active",
                "used": 0,
                "transactions": []
            }
            self.current_hold = hold
            self.holds.append(hold)
            return hold
    
    def update_hold(self, used_amount):
        with self.lock:
            if self.current_hold and self.current_hold["status"] == "active":
                used_amount = round(used_amount, 2)
                self.current_hold["remaining"] -= used_amount
                self.current_hold["used"] += used_amount
                self.current_hold["transactions"].append({
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "amount": used_amount
                })
                
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
            self.final_balance = total_cost
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

# Инициализация глобальных переменных
fueling_active = False
fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)
bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)
recipient_account = RecipientAccount(user_id="recipient1", initial_balance=0.0)
stub = None
total_liters = 0.0
total_cost = 0.0
stop_fueling = threading.Event()
packet_log = []
real_time_data = {"liters": 0.0, "balance": 0.0}
opkcmp = OPKCMP()
hold_manager = HoldManager()
fuel_price_per_liter = 54.37

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
        
        if not hold_manager.current_hold or hold_manager.current_hold["status"] != "active":
            hold_amount = liters * fuel_price_per_liter * 3
            hold_manager.create_hold(hold_amount, datetime.now().strftime("%H:%M:%S.%f")[:-3])
        
        start_time = time.time()
        if stub:
            response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
                fuel_price_per_liter=fuel_price_per_liter,
                liters=liters,
                is_finished=is_finished
            ))
        else:
            response = payment_pb2.FuelPaymentResponse(success=True)
        end_time = time.time()
        
        if response.success:
            used_amount = liters * fuel_price_per_liter
            hold_manager.update_hold(used_amount)
            
            if hold_manager.current_hold and hold_manager.current_hold["remaining"] < (liters * fuel_price_per_liter):
                new_hold_amount = liters * fuel_price_per_liter * 3
                hold_manager.create_hold(new_hold_amount, datetime.now().strftime("%H:%M:%S.%f")[:-3])
        
        return response, end_time - start_time
    except Exception as e:
        print(f"Payment error: {str(e)}")
        stop_fueling.set()
        return payment_pb2.FuelPaymentResponse(success=False), 0

def connect_to_grpc_server():
    global stub
    try:
        channel = grpc.insecure_channel('localhost:50051')
        grpc.channel_ready_future(channel).result(timeout=5)
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        print("GRPC connection established successfully")
        return True
    except Exception as e:
        print(f"GRPC connection error: {str(e)}")
        stub = None
        return False

def finalize_fueling():
    completion_packet = {
        "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "liters": 0,
        "balance": round(bank_account.get_balance(), 2),
        "is_final": True,
        "is_completion": True
    }
    
    packet_log.append(completion_packet)
    opkcmp.add_packet(completion_packet)
    opkcmp.process_final_packet(round(total_cost, 2))
    opkcmp.send_final_balance_to_recipient(recipient_account)
    
    if stub:
        process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)

def fueling_process():
    global total_liters, total_cost, stop_fueling, packet_log, real_time_data
    
    FRAME_INTERVAL = 0.001
    TARGET_PACKET_SIZE = 0.3
    frame_buffer = []
    buffer_liters = 0
    
    while not stop_fueling.is_set():
        try:
            fuel_consumed = fuel_pump.get_fuel_consumed(FRAME_INTERVAL)
            if fuel_consumed <= 0:
                time.sleep(FRAME_INTERVAL)
                continue
            
            cost = fuel_price_per_liter * fuel_consumed
            if not bank_account.withdraw(cost):
                stop_fueling.set()
                break
            
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            frame = {
                "time": current_time,
                "liters": fuel_consumed,
                "balance": bank_account.get_balance()
            }
            frame_buffer.append(frame)
            
            buffer_liters += fuel_consumed
            total_liters += fuel_consumed
            total_cost += cost
            
            real_time_data = {
                "liters": total_liters,
                "balance": bank_account.get_balance()
            }
            
            if buffer_liters >= TARGET_PACKET_SIZE:
                packet = {
                    "time": current_time,
                    "liters": buffer_liters,
                    "balance": bank_account.get_balance(),
                    "is_final": False,
                    "frames": frame_buffer.copy()
                }
                
                packet_log.append(packet)
                opkcmp.add_packet(packet)
                
                response, _ = process_fuel_payment(stub, fuel_price_per_liter, buffer_liters)
                if not response.success:
                    stop_fueling.set()
                    break
                
                buffer_liters = 0
                frame_buffer = []
            
            time.sleep(0.01)
            
        except Exception as e:
            logging.error(f"Fueling error: {str(e)}")
            stop_fueling.set()
            break

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

    finalize_fueling()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/toggle_fueling', methods=['POST'])
def toggle_fueling():
    global fueling_active, stop_fueling, packet_log, total_liters, total_cost
    
    if not fueling_active:
        fueling_active = True
        stop_fueling.clear()
        packet_log = []
        total_liters = 0.0
        total_cost = 0.0
        fuel_pump.start_pumping()
        threading.Thread(target=fueling_process).start()
        return jsonify({"status": "started"})
    else:
        fueling_active = False
        stop_fueling.set()
        fuel_pump.stop_pumping()
        return jsonify({"status": "stopped"})

@app.route('/get_fuel_data', methods=['GET'])
def get_fuel_data():
    holds_info = []
    for hold in hold_manager.get_holds(5):
        # Автоматически помечаем холды с остатком 0 как completed
        if hold['remaining'] <= 0 and hold['status'] != 'completed':
            hold['status'] = 'completed'
        holds_info.append({
            "id": hold["id"],
            "amount": hold["amount"],
            "used": hold["used"],
            "remaining": hold["remaining"],
            "status": hold["status"],
            "timestamp": hold["timestamp"],
            "progress": f"{hold['used']}/{hold['amount']}",
            "transactions": hold["transactions"][-3:]
        })
    
    current_hold = hold_manager.current_hold
    current_hold_info = {
        "id": current_hold["id"] if current_hold else None,
        "amount": current_hold["amount"] if current_hold else 0,
        "used": current_hold["used"] if current_hold else 0,
        "remaining": current_hold["remaining"] if current_hold else 0,
        "status": current_hold["status"] if current_hold else None
    } if current_hold else None
    
    return jsonify({
        "total_liters": round(total_liters, 3),
        "total_cost": round(total_cost, 2),
        "balance": round(bank_account.get_balance(), 2),
        "packet_log": packet_log[-10:],
        "real_time_data": {
            "liters": round(real_time_data["liters"], 3),
            "balance": round(real_time_data["balance"], 2)
        },
        "opkcmp_log": opkcmp.buffer[-10:],
        "recipient_balance": round(recipient_account.get_balance(), 2),
        "fueling_active": fueling_active,
        "holds": holds_info,
        "current_hold": current_hold_info
    })

@app.route('/add_fuel', methods=['POST'])
def add_fuel():
    data = request.json
    print(f"Received packet: {data['liters']} l, balance: {data['balance']} RUB")
    return jsonify({"status": "ok"})

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler('fuel_system.log', maxBytes=1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

if __name__ == '__main__':
    setup_logging()
    logging.info("Starting fuel system application")
    connect_to_grpc_server()
    app.run(debug=True, host='0.0.0.0', port=5000)