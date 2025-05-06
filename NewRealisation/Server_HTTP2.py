import grpc
from concurrent import futures
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
import time
import threading 
class BankSimulator:
    def __init__(self):
        self.balance = 1000000  # баланс в копейках (10 000 руб.)
        self.hold_amount = 0
        self.lock = threading.Lock()

    def make_hold(self, amount_kopecks):
        with self.lock:
            if self.balance >= amount_kopecks:
                self.hold_amount += amount_kopecks
                self.balance -= amount_kopecks
                print(f"✅ Холд установлен: {amount_kopecks / 100} руб.")
                return True
            else:
                print("❌ Недостаточно средств для холда")
                return False

    def release_hold(self):
        with self.lock:
            released = self.hold_amount
            self.hold_amount = 0
            print(f"🔓 Освобождено: {released / 100} руб.")
            return released

    def get_balance(self):
        with self.lock:
            return self.balance

bank = BankSimulator()
sessions = {}

class MicroPaymentServicer(pb2_grpc.MicroPaymentServiceServicer):
    def StreamPayments(self, request_iterator, context):
        session_id = None
        for req in request_iterator:
            session_id = req.session_id
            amount = req.amount_cents

            if session_id not in sessions:
                sessions[session_id] = {
                    "total": 0,
                    "hold": 10000,  # 100 рублей
                    "used": 0
                }
                print(f"[SERVER] Сессия начата: {session_id}")

            session = sessions[session_id]

            if session["used"] + amount > session["hold"]:
                print("[SERVER] Холд исчерпан → запрашиваем новый")
                bank.release_hold()
                bank.make_hold(10000)
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
        bank.release_hold()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_MicroPaymentServiceServicer_to_server(MicroPaymentServicer(), server)
    server.add_insecure_port('[::]:50051')
    print("[SERVER] gRPC сервер запущен на порту 50051...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()