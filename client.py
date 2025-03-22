import grpc
import payment_pb2
import payment_pb2_grpc
import threading
import time
from datetime import datetime  # Импортируем datetime для вывода времени
from bank_account import BankAccount  # Импортируем BankAccount

# Внешняя структура, имитирующая подачу топлива
class FuelPumpSimulator:
    def __init__(self, flow_rate_liters_per_second):
        self.flow_rate = flow_rate_liters_per_second  # Скорость подачи топлива (литров в секунду)
        self.total_fuel_dispensed = 0  # Общее количество выданного топлива
        self.is_pumping = False  # Флаг, указывающий, идет ли подача топлива

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
    # Отправка запроса на оплату бензина
    start_time = time.time()  # Засекаем время начала отправки
    response = stub.ProcessFuelPayment(payment_pb2.FuelPaymentRequest(
        fuel_price_per_liter=fuel_price_per_liter,
        liters=liters,
        is_finished=is_finished
    ))
    end_time = time.time()  # Засекаем время получения ответа
    return response, end_time - start_time  # Возвращаем ответ и время передачи

def fueling_process(stub, fuel_price_per_liter, fuel_pump, bank_account):
    total_liters = 0  # Общее количество заправленных литров
    total_cost = 0    # Общая стоимость заправки
    buffer_liters = 0  # Буфер для накопления литров перед отправкой кадра

    while not stop_fueling.is_set():
        # Получаем количество потребленного топлива за интервал времени
        time_interval = 0.3  # Интервал времени (секунды)
        fuel_consumed = fuel_pump.get_fuel_consumed(time_interval)
        buffer_liters += fuel_consumed

        # Если в буфере накопилось 0.3 литра или больше, отправляем кадр
        if buffer_liters >= 0.3:
            liters_to_send = 0.3
            cost = fuel_price_per_liter * liters_to_send

            # Снимаем средства со счета
            if bank_account.get_balance() >= cost:
                bank_account.withdraw(cost)
                current_time = datetime.now().strftime("%H:%M:%S")  # Получаем текущее время
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
                # Если средств недостаточно, отправляем оставшиеся литры
                remaining_balance = bank_account.get_balance()
                if remaining_balance > 0:
                    liters_to_send = remaining_balance / fuel_price_per_liter
                    if liters_to_send > 0:
                        bank_account.withdraw(remaining_balance)
                        current_time = datetime.now().strftime("%H:%M:%S")  # Получаем текущее время
                        print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {remaining_balance:.2f} RUB")
                        response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
                        if not response.success:
                            print("Fuel payment failed")
                        else:
                            total_liters += liters_to_send
                            total_cost += remaining_balance
                            print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")
                stop_fueling.set()  # Останавливаем заправку
                break

        # Проверяем баланс, если он равен нулю, завершаем заправку
        if bank_account.get_balance() <= 0:
            print("Balance is zero. Stopping fueling...")
            stop_fueling.set()
            break

        # Задержка для следующего измерения
        time.sleep(time_interval)

    # Отправляем оставшиеся литры, если они есть
    if buffer_liters > 0:
        # Отправляем только до 0.3 литра
        liters_to_send = min(buffer_liters, 0.3)
        cost = fuel_price_per_liter * liters_to_send

        if bank_account.get_balance() >= cost:
            bank_account.withdraw(cost)
            current_time = datetime.now().strftime("%H:%M:%S")  # Получаем текущее время
            print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {cost:.2f} RUB")
            response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
            if not response.success:
                print("Fuel payment failed")
            else:
                total_liters += liters_to_send
                total_cost += cost
                print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")
        else:
            # Если средств недостаточно, отправляем оставшиеся литры
            remaining_balance = bank_account.get_balance()
            if remaining_balance > 0:
                liters_to_send = remaining_balance / fuel_price_per_liter
                if liters_to_send > 0:
                    bank_account.withdraw(remaining_balance)
                    current_time = datetime.now().strftime("%H:%M:%S")  # Получаем текущее время
                    print(f"[{current_time}] Sending final frame: {liters_to_send:.4f} liters, {remaining_balance:.2f} RUB")
                    response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
                    if not response.success:
                        print("Fuel payment failed")
                    else:
                        total_liters += liters_to_send
                        total_cost += remaining_balance
                        print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")

    # Отправляем финальный кадр с флагом завершения
    current_time = datetime.now().strftime("%H:%M:%S")  # Получаем текущее время
    print(f"[{current_time}] Sending final frame to finish fueling...")
    response, transfer_time = process_fuel_payment(stub, fuel_price_per_liter, 0, is_finished=True)
    if response.success:
        print(f"Fueling finished successfully. Transfer time: {transfer_time:.4f} seconds.")
    else:
        print("Failed to finish fueling.")

def run():
    global stop_fueling
    stop_fueling = threading.Event()  # Флаг для остановки заправки

    # Подключение к серверу
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        fuel_price_per_liter = 54.37  # Цена за литр бензина

        # Создаем симулятор подачи топлива
        fuel_pump = FuelPumpSimulator(flow_rate_liters_per_second=6)  # 6 литров в секунду

        # Создаем банковский счет пользователя
        bank_account = BankAccount(user_id="user1", initial_balance=1000000.0)

        print("Welcome to the fuel station!")
        print(f"Initial balance: {bank_account.get_balance():.2f} RUB")
        print("Press 1 to start fueling, press 0 to stop.")

        # Запрашиваем у пользователя начало заправки
        user_input = input("Enter command (1 to start, 0 to stop): ")
        if user_input != "1":
            print("Fueling not started. Exiting...")
            return

        print("Fueling started. Press 0 to stop.")
        fuel_pump.start_pumping()

        # Запускаем процесс заправки в отдельном потоке
        fueling_thread = threading.Thread(target=fueling_process, args=(stub, fuel_price_per_liter, fuel_pump, bank_account))
        fueling_thread.start()

        # Ожидаем ввода пользователя для остановки заправки
        while True:
            user_input = input()
            if user_input == "0":
                print("Stopping fueling...")
                stop_fueling.set()  # Устанавливаем флаг остановки
                fuel_pump.stop_pumping()
                fueling_thread.join()  # Ожидаем завершения потока заправки
                break
            # Если баланс равен нулю, завершаем заправку
            if bank_account.get_balance() <= 0:
                print("Balance is zero. Stopping fueling...")
                stop_fueling.set()
                fuel_pump.stop_pumping()
                fueling_thread.join()
                break

if __name__ == '__main__':
    run()