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

class BankAccount:
    def __init__(self, user_id, initial_balance):
        self.user_id = user_id
        self.balance = initial_balance

    def get_balance(self):
        return self.balance

    def withdraw(self, amount):
        if amount <= self.balance:
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

class OPKCMP:
    def __init__(self):
        self.buffer = []
        self.final_packet_received = False
        self.final_balance = 0.0

    def add_packet(self, packet):
        self.buffer.append(packet)
        print(f"OPKCMP: Packet added to buffer. Time: {packet['time']}, Liters: {packet['liters']}, Balance: {packet['balance']}")

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

def process_fuel_payment(stub, fuel_price_per_liter, liters, is_finished=False):
    start_time = time.time()
    response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
        fuel_price_per_liter=fuel_price_per_liter,
        liters=liters,
        is_finished=is_finished
    ))
    end_time = time.time()
    return response, end_time - start_time

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
    channel = grpc.insecure_channel('localhost:50051')
    stub = payment_pb2_grpc.PaymentServiceStub(channel)

def fueling_process(stub, fuel_price_per_liter, fuel_pump, bank_account):
    global total_liters, total_cost, stop_fueling, packet_log, real_time_data, opkcmp, recipient_account
    buffer_liters = 0

    while not stop_fueling.is_set():
        time_interval = 0.1
        fuel_consumed = fuel_pump.get_fuel_consumed(0.01)
        buffer_liters += fuel_consumed
        total_liters += fuel_consumed

        cost = fuel_price_per_liter * fuel_consumed
        if bank_account.get_balance() >= cost:
            bank_account.withdraw(cost)
            total_cost += cost
        else:
            print("Insufficient funds. Stopping fueling...")
            stop_fueling.set()
            break

        real_time_data["liters"] = total_liters
        real_time_data["balance"] = bank_account.get_balance()

        if buffer_liters >= 0.3:
            liters_to_send = 0.3
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            packet = {
                "time": current_time,
                "liters": liters_to_send,
                "balance": bank_account.get_balance(),
                "is_final": False
            }
            packet_log.append(packet)
            opkcmp.add_packet(packet)

            response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
            if not response.success:
                print("Fuel payment failed")
                break

            buffer_liters -= liters_to_send

        time.sleep(time_interval)

    # Process remaining fuel and final packet
    if buffer_liters > 0:
        liters_to_send = buffer_liters
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        final_packet = {
            "time": current_time,
            "liters": liters_to_send,
            "balance": bank_account.get_balance(),
            "is_final": True
        }
        packet_log.append(final_packet)
        opkcmp.add_packet(final_packet)

    # Add completion packet
    current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    completion_packet = {
        "time": current_time,
        "liters": 0,
        "balance": bank_account.get_balance(),
        "is_final": True,
        "is_completion": True  # Special flag for completion packet
    }
    packet_log.append(completion_packet)
    opkcmp.add_packet(completion_packet)

    # Process final transaction
    opkcmp.process_final_packet(total_cost)  # Pass total_cost instead of balance
    opkcmp.send_final_balance_to_recipient(recipient_account)

    response, transfer_time = process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)
    if response.success:
        print(f"Fueling finished successfully. Transfer time: {transfer_time:.4f} seconds.")
    else:
        print("Failed to finish fueling.")

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
        "fueling_active": fueling_active  # Add fueling status to response
    })

if __name__ == '__main__':
    connect_to_grpc_server()
    fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)
    bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)
    fuel_price_per_liter = 54.37
    app.run(debug=True)