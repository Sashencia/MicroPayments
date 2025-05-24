import grpc
from concurrent import futures
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
import threading
import sqlite3

def init_db():
    conn = sqlite3.connect('gas_stations.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS gas_stations (
                      station_id INTEGER PRIMARY KEY,
                      name TEXT NOT NULL,
                      location TEXT NOT NULL,
                      fuel_type TEXT NOT NULL,
                      price_per_liter REAL NOT NULL)''')

    # Вставляем тестовые данные
    stations = [
        (1, "Лукойл", "Москва", "АИ-95", 54.30),
        (2, "Газпром", "Санкт-Петербург", "АИ-92", 52.70),
        (3, "Роснефть", "Екатеринбург", "ДТ", 56.80),
        (4, "Татнефть", "Казань", "АИ-98", 59.50)
    ]
    cursor.executemany("INSERT OR IGNORE INTO gas_stations VALUES (?, ?, ?, ?, ?)", stations)
    conn.commit()
    conn.close()

def get_fuel_price(station_id):
    conn = sqlite3.connect('gas_stations.db')
    cursor = conn.cursor()
    cursor.execute("SELECT price_per_liter FROM gas_stations WHERE station_id=?", (station_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

class BankSimulator:
    def __init__(self):
        self.balance = 1000000  # 10 000 рублей в копейках
        self.holds = {}  # {session_id: amount_kopecks}
        self.lock = threading.Lock()

    def make_hold(self, session_id, amount_kopecks):
        with self.lock:
            if self.balance >= amount_kopecks:
                self.holds[session_id] = amount_kopecks
                self.balance -= amount_kopecks
                print(f"✅ Холд установлен ({session_id}): {amount_kopecks / 100} руб.")
                return True
            else:
                print("❌ Недостаточно средств для холда")
                return False

    def release_hold(self, session_id):
        with self.lock:
            released = self.holds.pop(session_id, 0)
            self.balance += released
            print(f"🔓 Освобождено ({session_id}): {released / 100} руб.")
            return released


bank = BankSimulator()
sessions = {}


class MicroPaymentServicer(pb2_grpc.MicroPaymentServiceServicer):
    def StreamPayments(self, request_iterator, context):
        session_id = None

        for req in request_iterator:
            session_id = req.session_id
            station_id = req.station_id
            amount_liters = req.amount_liters  # количество литров от клиента

            # Получаем цену за литр из базы данных
            price_per_liter = get_fuel_price(station_id)
            if not price_per_liter:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Заправка с ID {station_id} не найдена")
                return pb2.PaymentResponse(success=False)

            # Переводим в копейки: 1 рубль = 100 копеек
            amount_cents = int(amount_liters * price_per_liter * 100)

            # Проверяем, есть ли такая сессия
            if session_id in sessions:
                session = sessions[session_id]
            else:
                # Создаём новую сессию и ставим холд
                sessions[session_id] = {
                    "total": 0,
                    "hold": 10000,  # 100 рублей в копейках
                    "used": 0
                }
                success = bank.make_hold(session_id, 10000)
                if not success:
                    context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                    context.set_details("Не удалось установить холд")
                    return pb2.PaymentResponse(success=False)

            session = sessions[session_id]

            # Если текущий холд исчерпан — освобождаем его и создаём новый
            if session["used"] + amount_cents > session["hold"]:
                print("[SERVER] Холд исчерпан → запрашиваем новый")
                bank.release_hold(session_id)
                bank.make_hold(session_id, 10000)
                session["hold"] = 10000
                session["used"] = 0

            # Обновляем состояние сессии
            session["used"] += amount_cents
            session["total"] += amount_cents

            print(f"[SERVER] Платёж обработан: {amount_cents / 100} руб. ({amount_liters} л.). Итого: {session['total'] / 100} руб.")

            # Отправляем ответ клиенту
            yield pb2.PaymentResponse(
                success=True,
                total_charged=session["total"],
                remaining_hold=session["hold"] - session["used"]
            )

        # После завершения потока — очищаем данные
        if session_id:
            print(f"[SERVER] Сессия завершена: {session_id}. Итого: {session['total'] / 100} руб.")
            del sessions[session_id]
            bank.release_hold(session_id)
def serve():
    # Загружаем TLS-сертификаты
    with open('server.key', 'rb') as f:
        private_key = f.read()
    with open('server.crt', 'rb') as f:
        certificate_chain = f.read()

    server_credentials = grpc.ssl_server_credentials(
        [(private_key, certificate_chain)],
        root_certificates=None,
        require_client_auth=False
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_MicroPaymentServiceServicer_to_server(MicroPaymentServicer(), server)
    server.add_secure_port('[::]:50051', server_credentials)
    print("🚀 gRPC сервер запущен на порту 50051 (TLS/SSL)")
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    init_db()  # <-- Добавить эту строку
    serve()