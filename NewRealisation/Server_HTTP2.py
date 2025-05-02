import grpc
from concurrent import futures
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
import time

class BankSimulator:
    def __init__(self):
        self.balance = 100000  # в копейках (1000 руб.)
        self.hold = 0

    def make_hold(self, amount):
        if self.balance >= amount:
            self.hold += amount
            self.balance -= amount
            return True
        return False

    def charge(self, amount):
        if amount <= self.hold:
            self.hold -= amount
            return True
        return False

    def release_hold(self):
        self.balance += self.hold
        released = self.hold
        self.hold = 0
        return released

class MicroPaymentServicer(pb2_grpc.MicroPaymentServiceServicer):
    def __init__(self):
        self.sessions = {}  # session_id → { hold_amount, used }

    def StreamPayments(self, request_iterator, context):
        session_id = f"sess_{int(time.time())}"
        bank = BankSimulator()
        bank.make_hold(1000)  # холд 10 рублей
        self.sessions[session_id] = {"hold": bank.hold, "used": 0}

        print(f"[SERVER] Session started: {session_id}, Hold: {bank.hold} cents")

        for req in request_iterator:
            if req.session_id != session_id:
                continue

            if bank.hold < 500:  # если холд меньше 5 рублей
                print("[SERVER] Renewing hold...")
                bank.release_hold()
                bank.make_hold(1000)

            if bank.charge(req.amount_cents):
                self.sessions[session_id]["used"] += req.amount_cents
                print(f"[SERVER] Charged: {req.amount_cents / 100} руб. Total: {bank.hold - bank.balance}")
                yield pb2.PaymentResponse(
                    success=True,
                    total_charged=self.sessions[session_id]["used"],
                    remaining_hold=bank.hold
                )
            else:
                print("[SERVER] Charge failed")
                yield pb2.PaymentResponse(success=False)

        # Сессия завершена
        refund = bank.release_hold()
        print(f"[SERVER] Session ended: {session_id}. Refunded: {refund / 100} руб.")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_MicroPaymentServiceServicer_to_server(MicroPaymentServicer(), server)
    server.add_insecure_port('[::]:50051')
    print("[SERVER] gRPC сервер запущен на порту 50051...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()