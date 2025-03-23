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

# BankAccount class to simulate user's bank account
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

# FuelPumpSimulator class to simulate fuel pumping
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

# Function to process fuel payment via gRPC
def process_fuel_payment(stub, fuel_price_per_liter, liters, is_finished=False):
    start_time = time.time()
    response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
        fuel_price_per_liter=fuel_price_per_liter,
        liters=liters,
        is_finished=is_finished
    ))
    end_time = time.time()
    return response, end_time - start_time

# Flask app
app = Flask(__name__)

# Global variables
fueling_active = False
fuel_pump = None
stub = None
total_liters = 0.0
total_cost = 0.0
stop_fueling = threading.Event()
packet_log = []  # Log for packet sending
real_time_data = {  # Real-time fueling data
    "liters": 0.0,
    "balance": 0.0
}

# Connect to gRPC server
def connect_to_grpc_server():
    global stub
    channel = grpc.insecure_channel('localhost:50051')
    stub = payment_pb2_grpc.PaymentServiceStub(channel)

# Fueling process
def fueling_process(stub, fuel_price_per_liter, fuel_pump, bank_account):
    global total_liters, total_cost, stop_fueling, packet_log, real_time_data
    buffer_liters = 0  # Buffer for accumulated liters before sending a packet

    while not stop_fueling.is_set():
        time_interval = 0.1  # Time interval in seconds
        fuel_consumed = fuel_pump.get_fuel_consumed(0.01)
        buffer_liters += fuel_consumed
        total_liters += fuel_consumed

        # Deduct funds from the account with precision up to kopecks
        cost = fuel_price_per_liter * fuel_consumed
        if bank_account.get_balance() >= cost:
            bank_account.withdraw(cost)
            total_cost += cost
        else:
            print("Insufficient funds. Stopping fueling...")
            stop_fueling.set()
            break

        # Update real-time data
        real_time_data["liters"] = total_liters
        real_time_data["balance"] = bank_account.get_balance()

        # If buffer has accumulated 0.3 liters or more, send a packet
        if buffer_liters >= 0.3:
            liters_to_send = 0.3
            cost_to_send = fuel_price_per_liter * liters_to_send

            # Log packet sending
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            packet_log.append({
                "time": current_time,
                "liters": liters_to_send,
                "balance": bank_account.get_balance()
            })
            response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
            if not response.success:
                print("Fuel payment failed")
                break

            # Update buffer
            buffer_liters -= liters_to_send

        # Delay for the next measurement
        time.sleep(time_interval)

    # Send remaining liters in the buffer
    if buffer_liters > 0:
        liters_to_send = buffer_liters
        cost_to_send = fuel_price_per_liter * liters_to_send

        # Log final packet
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        packet_log.append({
            "time": current_time,
            "liters": liters_to_send,
            "balance": bank_account.get_balance()
        })
        response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
        if not response.success:
            print("Fuel payment failed")
        else:
            total_liters += liters_to_send
            total_cost += cost_to_send

    # Send final frame to finish fueling
    current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    packet_log.append({
        "time": current_time,
        "liters": 0,
        "balance": bank_account.get_balance()
    })
    response, transfer_time = process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)
    if response.success:
        print(f"Fueling finished successfully. Transfer time: {transfer_time:.4f} seconds.")
    else:
        print("Failed to finish fueling.")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/toggle_fueling', methods=['POST'])
def toggle_fueling():
    global fueling_active, fuel_pump, stop_fueling, packet_log
    if not fueling_active:
        fueling_active = True
        stop_fueling.clear()
        packet_log = []
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
    global total_liters, total_cost, bank_account, packet_log, real_time_data
    return jsonify({
        "total_liters": total_liters,
        "total_cost": total_cost,
        "balance": bank_account.get_balance(),
        "packet_log": packet_log[-10:],  # Last 10 entries
        "real_time_data": real_time_data  # Real-time fueling data
    })

# Main
if __name__ == '__main__':
    connect_to_grpc_server()
    fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)  # 6 liters per second
    bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)
    fuel_price_per_liter = 54.37  # Price per liter of fuel
    app.run(debug=True)