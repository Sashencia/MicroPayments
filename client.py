import grpc
import payment_pb2
import payment_pb2_grpc
from datetime import datetime
import threading
import time

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
        self.flow_rate = flow_rate_liters_per_second  # Fuel flow rate (liters per second)
        self.total_fuel_dispensed = 0  # Total fuel dispensed
        self.is_pumping = False  # Flag to indicate if pumping is active

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
    start_time = time.time()  # Start time for transfer
    response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
        fuel_price_per_liter=fuel_price_per_liter,
        liters=liters,
        is_finished=is_finished
    ))
    end_time = time.time()  # End time for transfer
    return response, end_time - start_time  # Return response and transfer time

# Function to simulate the fueling process
def fueling_process(stub, fuel_price_per_liter, fuel_pump, bank_account):
    total_liters = 0  # Total liters fueled
    total_cost = 0    # Total cost of fueling
    buffer_liters = 0  # Buffer for accumulated liters

    while not stop_fueling.is_set():
        # Get fuel consumed in the time interval
        time_interval = 0.2  # Time interval in seconds
        fuel_consumed = fuel_pump.get_fuel_consumed(time_interval)
        buffer_liters += fuel_consumed

        # Send a frame if buffer has 0.3 liters or more
        if buffer_liters >= 0.3:
            liters_to_send = 0.3
            cost = fuel_price_per_liter * liters_to_send

            # Withdraw funds from the bank account
            if bank_account.get_balance() >= cost:
                bank_account.withdraw(cost)
                current_time = datetime.now().strftime("%H:%M:%S")  # Current time
                print(f"[{current_time}] Sending frame: {liters_to_send:.2f} liters, {cost:.2f} RUB")
                response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
                if not response.success:
                    print("Fuel payment failed")
                    break
                total_liters += liters_to_send
                total_cost += cost
                buffer_liters -= liters_to_send
                print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")
            else:
                # If balance is insufficient, send remaining liters
                remaining_balance = bank_account.get_balance()
                if remaining_balance > 0:
                    liters_to_send = remaining_balance / fuel_price_per_liter
                    if liters_to_send > 0:
                        bank_account.withdraw(remaining_balance)
                        current_time = datetime.now().strftime("%H:%M:%S")  # Current time
                        print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {remaining_balance:.2f} RUB")
                        response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
                        if not response.success:
                            print("Fuel payment failed")
                        else:
                            total_liters += liters_to_send
                            total_cost += remaining_balance
                            print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")
                stop_fueling.set()  # Stop fueling
                break

        # Check if balance is zero
        if bank_account.get_balance() <= 0:
            print("Balance is zero. Stopping fueling...")
            stop_fueling.set()
            break

        # Delay for the next measurement
        time.sleep(time_interval)

    # Send remaining liters in the buffer
    if buffer_liters > 0:
        liters_to_send = min(buffer_liters, 0.3)
        cost = fuel_price_per_liter * liters_to_send

        if bank_account.get_balance() >= cost:
            bank_account.withdraw(cost)
            current_time = datetime.now().strftime("%H:%M:%S")  # Current time
            print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {cost:.2f} RUB")
            response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
            if not response.success:
                print("Fuel payment failed")
            else:
                total_liters += liters_to_send
                total_cost += cost
                print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")
        else:
            # If balance is insufficient, send remaining liters
            remaining_balance = bank_account.get_balance()
            if remaining_balance > 0:
                liters_to_send = remaining_balance / fuel_price_per_liter
                if liters_to_send > 0:
                    bank_account.withdraw(remaining_balance)
                    current_time = datetime.now().strftime("%H:%M:%S")  # Current time
                    print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {remaining_balance:.2f} RUB")
                    response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
                    if not response.success:
                        print("Fuel payment failed")
                    else:
                        total_liters += liters_to_send
                        total_cost += remaining_balance
                        print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")

    # Send final frame to finish fueling
    current_time = datetime.now().strftime("%H:%M:%S")  # Current time
    print(f"[{current_time}] Sending final frame to finish fueling...")
    response, transfer_time = process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)
    if response.success:
        print(f"Fueling finished successfully. Transfer time: {transfer_time:.4f} seconds.")
    else:
        print("Failed to finish fueling.")

# Main function to run the simulation
def run():
    global stop_fueling
    stop_fueling = threading.Event()  # Flag to stop fueling

    # Connect to the gRPC server
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        fuel_price_per_liter = 54.37  # Fuel price per liter

        # Create fuel pump simulator
        fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)  # 6 liters per second

        # Create user's bank account
        bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)

        print("Welcome to the fuel station!")
        print(f"Initial balance: {bank_account.get_balance():.2f} RUB")
        print("Press 1 to start fueling, press 0 to stop.")

        # Get user input to start fueling
        user_input = input("Enter command (1 to start, 0 to stop): ")
        if user_input != "1":
            print("Fueling not started. Exiting...")
            return

        print("Fueling started. Press 0 to stop.")
        fuel_pump.start_pumping()

        # Start fueling process in a separate thread
        fueling_thread = threading.Thread(target=fueling_process, args=(stub, fuel_price_per_liter, fuel_pump, bank_account))
        fueling_thread.start()

        # Wait for user input to stop fueling
        while True:
            user_input = input()
            if user_input == "0":
                print("Stopping fueling...")
                stop_fueling.set()  # Set stop flag
                fuel_pump.stop_pumping()
                fueling_thread.join()  # Wait for the thread to finish
                break
            # Stop fueling if balance is zero
            if bank_account.get_balance() <= 0:
                print("Balance is zero. Stopping fueling...")
                stop_fueling.set()
                fuel_pump.stop_pumping()
                fueling_thread.join()
                break

if __name__ == '__main__':
    run()