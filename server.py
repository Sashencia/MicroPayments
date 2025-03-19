import grpc
from concurrent import futures
import payment_pb2
import payment_pb2_grpc
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import signal
import sys
from datetime import datetime

class PaymentService(payment_pb2_grpc.PaymentServiceServicer):
    def __init__(self):
        self.transactions = []  # Локальный массив для хранения транзакций
        self.users = {
            "user1": self.get_public_key("user1"),
            "user2": self.get_public_key("user2"),
        }
        self.hold_amount = 100  # Начальный холд в 100 рублей
        self.used_amount = 0    # Использованная сумма
        self.total_fuel_cost = 0  # Общая стоимость заправки

    def CreateTransaction(self, request, context):
        public_key = self.users.get(request.sender_id)
        if not public_key:
            return payment_pb2.TransactionResponse(success=False, transaction_id="")

        try:
            # Проверка подписи транзакции
            public_key.verify(
                request.signature,
                f"{request.sender_id}{request.receiver_id}{request.amount}".encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            transaction_id = f"txn_{len(self.transactions) + 1}"
            self.transactions.append({
                "id": transaction_id,
                "sender_id": request.sender_id,
                "receiver_id": request.receiver_id,
                "amount": request.amount,
                "signature": request.signature.hex()
            })
            print(f"Transaction created: ID={transaction_id}, Sender={request.sender_id}, "
                  f"Receiver={request.receiver_id}, Amount={request.amount}")
            return payment_pb2.TransactionResponse(success=True, transaction_id=transaction_id)
        except Exception as e:
            print(f"Transaction failed: {e}")
            return payment_pb2.TransactionResponse(success=False, transaction_id="")

    def VerifyTransaction(self, request, context):
        transaction = next((txn for txn in self.transactions if txn["id"] == request.transaction_id), None)
        if transaction:
            print(f"Transaction verified: ID={request.transaction_id}")
            return payment_pb2.VerifyResponse(success=True, message="Transaction verified")
        else:
            print(f"Transaction not found: ID={request.transaction_id}")
            return payment_pb2.VerifyResponse(success=False, message="Transaction not found")

    def ProcessFuelPayment(self, request, context):
        fuel_price_per_liter = request.fuel_price_per_liter
        liters = request.liters
        cost = fuel_price_per_liter * liters

        if request.is_finished:
            print("Fueling finished.")
            return payment_pb2.FuelPaymentResponse(success=True, message="Fueling finished")

        if self.used_amount + cost > self.hold_amount:
            print("Insufficient hold amount. Requesting new hold...")
            self.hold_amount = 100  # Новый холд
            self.used_amount = 0
            print(f"New hold: {self.hold_amount} RUB")

        self.used_amount += cost
        self.total_fuel_cost += cost  # Обновляем общую стоимость заправки
        print(f"Fuel payment processed: {liters:.2f} liters, {cost:.2f} RUB. "
              f"Used amount: {self.used_amount:.2f} RUB, Remaining hold: {self.hold_amount - self.used_amount:.2f} RUB")
        print(f"Total fuel cost: {self.total_fuel_cost:.2f} RUB")  # Выводим общую стоимость

        return payment_pb2.FuelPaymentResponse(success=True, message="Fuel payment processed")

    def get_public_key(self, user_id):
        # Загрузка открытого ключа из файла
        with open(f"{user_id}_public.pem", "rb") as key_file:
            public_key = serialization.load_pem_public_key(
                key_file.read(),
                backend=default_backend()
            )
        return public_key

def handle_sigint(signum, frame):
    print("\nServer is shutting down...")
    sys.exit(0)

def serve():
    # Обработка сигнала SIGINT (Ctrl + C)
    signal.signal(signal.SIGINT, handle_sigint)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port('[::]:50051')
    print("Server started on port 50051...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()