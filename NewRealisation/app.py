from flask import Flask, render_template, jsonify
import grpc
import threading
import time

import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc

app = Flask(__name__)

# === Эмуляция банковского аккаунта ===
class BankAccount:
    def __init__(self):
        self.balance = 100000  # 1000 руб. в копейках
        self.lock = threading.Lock()

    def get_balance(self):
        with self.lock:
            return self.balance

    def withdraw(self, amount):
        with self.lock:
            if self.balance >= amount:
                self.balance -= amount
                return True
            return False

# === Глобальные переменные ===
bank_account = BankAccount()
stub = None
session_id = ""
total_used = 0.0
stop_streaming = threading.Event()
real_time_data = {"used": 0.0, "balance": 0.0}

# === Подключение к gRPC ===
def connect_to_grpc():
    global stub
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = pb2_grpc.MicroPaymentServiceStub(channel)
        return True
    except:
        stub = None
        return False

# === Потоковая отправка платежей ===
def streaming_process(session_id):
    global total_used, real_time_data
    while not stop_streaming.is_set():
        amount_cents = 10  # 10 копеек
        if bank_account.withdraw(amount_cents):
            total_used += amount_cents
            print(f"💸 Отправлено: {amount_cents / 100} руб.")
            try:
                stub.StreamPayments(iter([
                    pb2.PaymentRequest(session_id=session_id, amount_cents=amount_cents)
                ]))
            except:
                print("❌ Ошибка передачи")
                stop_streaming.set()
                break
        else:
            print("🚫 Недостаточно средств")
            stop_streaming.set()
            break

        time.sleep(0.5)

    print("🏁 Сессия завершена")
    real_time_data["used"] = round(total_used / 100, 2)
    real_time_data["balance"] = round(bank_account.get_balance() / 100, 2)

# === API ===
@app.route('/')
def index():
    return render_template('html.html')

@app.route('/start', methods=['POST'])
def start_session():
    global session_id, total_used, stop_streaming
    session_id = f"sess_{int(time.time())}"
    total_used = 0.0
    stop_streaming.clear()
    threading.Thread(target=streaming_process, args=(session_id,), daemon=True).start()
    return jsonify({"session_id": session_id})

@app.route('/stop', methods=['POST'])
def stop_session():
    stop_streaming.set()
    return jsonify({"status": "stopped"})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "used": round(total_used / 100, 2),
        "balance": round(bank_account.get_balance() / 100, 2),
        "session_id": session_id
    })

# === Запуск приложения ===
if __name__ == '__main__':
    connect_to_grpc()
    app.run(debug=True, port=5000)