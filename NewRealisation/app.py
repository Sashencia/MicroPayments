from flask import Flask, render_template, jsonify, request
import grpc
import threading
import time
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc

app = Flask(__name__)

# === Эмуляция банковского аккаунта ===
class BankAccount:
    def __init__(self, user_id, initial_balance_kopecks):
        self.user_id = user_id
        self.balance = initial_balance_kopecks  # Всё храним в копейках
        self.hold = 0
        self.used_hold = 0
        self.lock = threading.Lock()

    def get_balance(self):
        with self.lock:
            return self.balance / 100

    def make_hold(self, amount_kopecks):
        with self.lock:
            if self.balance >= amount_kopecks:
                self.hold += amount_kopecks
                self.balance -= amount_kopecks
                self.used_hold = 0
                print(f"✅ Холд установлен: {amount_kopecks / 100} руб.")
                return True
            else:
                print("❌ Недостаточно средств для холда")
                return False

    def charge_from_hold(self, amount_kopecks):
        with self.lock:
            if self.used_hold + amount_kopecks > self.hold:
                return False
            self.used_hold += amount_kopecks
            return True

    def release_hold(self):
        with self.lock:
            released = self.hold - self.used_hold
            self.balance += released
            print(f"🔓 Разморожено: {released / 100} руб.")
            self.hold = 0
            self.used_hold = 0
            return released

    def get_total_hold(self):
        return self.hold / 100

    def get_used_hold(self):
        return self.used_hold / 100

    def get_remaining_hold(self):
        return (self.hold - self.used_hold) / 100


# === Класс получателя (сервис или банк) ===
class RecipientAccount:
    def __init__(self, user_id):
        self.user_id = user_id
        self.balance = 0.0  # в рублях

    def deposit(self, amount_rub):
        self.balance += amount_rub
        print(f"📥 Получено: {amount_rub:.2f} руб. Баланс: {self.balance:.2f} руб.")

    def get_balance(self):
        return self.balance


# === Глобальные переменные ===
bank_account = BankAccount(user_id="user1", initial_balance_kopecks=1000000)  # 10000 рублей
recipient_account = RecipientAccount(user_id="service_owner")
stub = None
session_id = ""
total_used = 0.0  # всего использовано в рублях
stop_streaming = threading.Event()
real_time_data = {"used": 0.0, "balance": 0.0}


# === Подключение к gRPC серверу ===
def connect_to_grpc():
    global stub
    try:
        channel = grpc.insecure_channel('localhost:50051')
        grpc.channel_ready_future(channel).result(timeout=5)
        stub = pb2_grpc.MicroPaymentServiceStub(channel)
        print("✅ Подключено к gRPC серверу")
        return True
    except Exception as e:
        print(f"❌ Не удалось подключиться к gRPC: {e}")
        stub = None
        return False


# === Функция потоковой отправки платежей ===
def streaming_process(session_id):
    global total_used, real_time_data
    base_amount_kopecks = 10  # 10 копеек за шаг
    hold_amount_kopecks = 10000  # 100 рублей

    # Устанавливаем первый холд, если его нет
    if bank_account.hold == 0:
        success = bank_account.make_hold(hold_amount_kopecks)
        if not success:
            print("🚫 Не удалось установить холд")
            stop_streaming.set()
            return

    while not stop_streaming.is_set():
        # Если израсходовано более 2/3 текущего холда → создаём новый
        if bank_account.get_used_hold() >= bank_account.get_total_hold() * 2 / 3:
            print("🔔 Требуется новый холд")
            bank_account.release_hold()
            bank_account.make_hold(hold_amount_kopecks)

        # Списываем из холда
        if bank_account.charge_from_hold(base_amount_kopecks):
            real_time_data["used"] += base_amount_kopecks / 100
            real_time_data["balance"] = bank_account.get_balance()
            print(f"💸 Отправлено: {base_amount_kopecks / 100} руб. "
                  f"Осталось в холде: {bank_account.get_remaining_hold()} руб.")

            try:
                stub.StreamPayments(iter([
                    pb2.PaymentRequest(session_id=session_id, amount_cents=base_amount_kopecks)
                ]))
            except Exception as e:
                print("Ошибка при отправке:", e)
                stop_streaming.set()
                break
        else:
            print("🚫 Недостаточно средств в холде")
            stop_streaming.set()
            break

        time.sleep(0.005)

    # Освобождаем остаток холда и завершаем сессию
    print("🏁 Сессия завершена. Остаток холда освобождён.")
    bank_account.release_hold()


# === API маршруты ===
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start_session():
    global session_id, stop_streaming
    session_id = f"sess_{int(time.time())}"
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
        "balance": round(bank_account.get_balance(), 2),
        "hold": round(bank_account.get_total_hold(), 2),
        "used": round(bank_account.get_used_hold(), 2),
        "remaining": round(bank_account.get_remaining_hold(), 2),
        "needs_new_hold": bank_account.get_used_hold() >= bank_account.get_total_hold() * 2 / 3,
        "total_used": round(real_time_data["used"], 2)
    })


# === Запуск приложения ===
if __name__ == '__main__':
    connect_to_grpc()
    app.run(debug=True, port=5000)