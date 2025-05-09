import grpc
from concurrent import futures
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
import threading

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
            amount = req.amount_cents

            if session_id in sessions:
                session = sessions[session_id]
            else:
                sessions[session_id] = {
                    "total": 0,
                    "hold": 10000,  # 100 рублей
                    "used": 0
                }
                success = bank.make_hold(session_id, 10000)
                if not success:
                    context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                    context.set_details("Не удалось установить холд")
                    return pb2.PaymentResponse(success=False)

            session = sessions[session_id]

            if session["used"] + amount > session["hold"]:
                print("[SERVER] Холд исчерпан → запрашиваем новый")
                bank.release_hold(session_id)
                bank.make_hold(session_id, 10000)
                session["hold"] = 10000
                session["used"] = 0

            session["used"] += amount
            session["total"] += amount

            print(f"[SERVER] Платёж обработан: {amount / 100} руб. Итого: {session['total'] / 100} руб.")

            yield pb2.PaymentResponse(
                success=True,
                total_charged=session["total"],
                remaining_hold=session["hold"] - session["used"]
            )

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
    serve()