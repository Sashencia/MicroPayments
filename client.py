import grpc
import payment_pb2
import payment_pb2_grpc
import threading
import time
from datetime import datetime

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

def fueling_process(stub, fuel_price_per_liter, fuel_pump):
    total_liters = 0  # Общее количество заправленных литров
    total_cost = 0    # Общая стоимость заправки
    buffer_liters = 0  # Буфер для накопления литров перед отправкой кадра

    while not stop_fueling.is_set():
        # Получаем количество потребленного топлива за интервал времени
        time_interval = 0.05  # Интервал времени (секунды)
        fuel_consumed = fuel_pump.get_fuel_consumed(time_interval)
        buffer_liters += fuel_consumed

        # Если в буфере накопилось 0.3 литра или больше, отправляем кадр
        if buffer_liters >= 0.3:
            liters_to_send = 0.3
            print(f"Sending frame: {liters_to_send:.2f} liters, {fuel_price_per_liter * liters_to_send:.2f} RUB")
            response, _ = process_fuel_payment(stub, fuel_price_per_liter, liters_to_send)
            if not response.success:
                print("Fuel payment failed")
                break
            total_liters += liters_to_send
            total_cost += fuel_price_per_liter * liters_to_send
            buffer_liters -= liters_to_send
            print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")

        # Задержка для следующего измерения
        time.sleep(time_interval)

    # Отправляем оставшиеся литры, если они есть
    if buffer_liters > 0:
        print(f"Sending final frame: {buffer_liters:.2f} liters, {fuel_price_per_liter * buffer_liters:.2f} RUB")
        response, _ = process_fuel_payment(stub, fuel_price_per_liter, buffer_liters)
        if not response.success:
            print("Fuel payment failed")
        else:
            total_liters += buffer_liters
            total_cost += fuel_price_per_liter * buffer_liters
            print(f"Total fueled: {total_liters:.2f} liters, Total cost: {total_cost:.2f} RUB")

    # Отправляем финальный кадр с флагом завершения
    print("Sending final frame to finish fueling...")
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

        print("Welcome to the fuel station!")
        print("Press 1 to start fueling, press 0 to stop.")

        # Запрашиваем у пользователя начало заправки
        user_input = input("Enter command (1 to start, 0 to stop): ")
        if user_input != "1":
            print("Fueling not started. Exiting...")
            return

        print("Fueling started. Press 0 to stop.")
        fuel_pump.start_pumping()

        # Запускаем процесс заправки в отдельном потоке
        fueling_thread = threading.Thread(target=fueling_process, args=(stub, fuel_price_per_liter, fuel_pump))
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

if __name__ == '__main__':
    run()