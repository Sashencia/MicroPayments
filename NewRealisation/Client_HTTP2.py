import grpc
import payment_pb2
import payment_pb2_grpc
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.backends import default_backend
import threading
import time
import datetime

# Эмуляция банковского аккаунта
class BankAccount:
    def __init__(self, user_id, initial_balance_kopecks):
        self.user_id = user_id
        self.balance = initial_balance_kopecks  # хранится в копейках

    def get_balance(self):
        return self.balance / 100  # в рублях

    def get_balance_kopecks(self):
        return self.balance  # в копейках

    def withdraw(self, amount_kopecks):
        if amount_kopecks <= self.balance:
            self.balance -= amount_kopecks
            return True
        return False

    def sign_data(self, data: str) -> bytes:
        with open(f"{self.user_id}_private.pem", "rb") as key_file:
            private_key = load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
        signature = private_key.sign(
            data.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return signature


# Флаг остановки
stop_streaming = threading.Event()

# Функция отправки платежей по потоку
def stream_payments(stub, session_id, cost_per_unit_kopecks, bank_account, interval=0.5):
    while not stop_streaming.is_set():
        if bank_account.get_balance_kopecks() < cost_per_unit_kopecks:
            print("Недостаточно средств. Завершаем сессию.")
            break

        bank_account.withdraw(cost_per_unit_kopecks)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Отправляем платёж: {cost_per_unit_kopecks / 100} руб.")

        request = payment_pb2.PaymentRequest(
            session_id=session_id,
            amount=cost_per_unit_kopecks
        )

        try:
            stub.StreamPayments(iter([request]))
        except Exception as e:
            print("Ошибка при отправке платежа:", e)
            break

        time.sleep(interval)

    # Завершаем сессию
    print("Завершаем сессию...")
    try:
        # Посылаем финальный пакет
        stub.StreamPayments(iter([
            payment_pb2.PaymentRequest(session_id=session_id, amount=0)
        ]))
    finally:
        print("Сессия завершена.")


# Создание транзакции
def create_transaction(stub, sender, receiver, amount_kopecks):
    data_to_sign = f"{sender}{receiver}{amount_kopecks}"
    signature = sender.sign_data(data_to_sign)

    response = stub.CreateTransaction(payment_pb2.TransactionRequest(
        sender_id=sender.user_id,
        receiver_id=receiver,
        amount=amount_kopecks,
        signature=signature
    ))

    if response.success:
        print(f"Транзакция создана: {response.transaction_id}")
    else:
        print("Ошибка создания транзакции")


# Проверка транзакции
def verify_transaction(stub, transaction_id):
    response = stub.VerifyTransaction(payment_pb2.TransactionVerifyRequest(
        transaction_id=transaction_id
    ))
    print(f"Результат проверки: {response.message}")


# Основная функция
def run():
    global stop_streaming
    stop_streaming = threading.Event()

    with grpc.insecure_channel('localhost:50051') as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)

        # Настройка пользователя
        user = BankAccount(user_id="user1", initial_balance_kopecks=10000)  # 100 рублей
        service_id = "service_video"

        print("Добро пожаловать в систему микроплатежей!")
        print(f"Ваш баланс: {user.get_balance():.2f} руб.")

        print("Выберите действие:")
        print("1 - Начать стриминг (платить каждые 0.5 секунды по 10 коп.)")
        print("2 - Создать транзакцию")
        print("3 - Проверить транзакцию")

        choice = input("Введите номер действия: ")

        if choice == "1":
            session_id = f"session_{int(time.time())}"
            print(f"Начата сессия: {session_id}")

            streaming_thread = threading.Thread(
                target=stream_payments,
                args=(stub, session_id, 10, user),
                daemon=True
            )
            streaming_thread.start()

            input("Нажмите Enter для завершения...\n")
            stop_streaming.set()
            streaming_thread.join()

        elif choice == "2":
            receiver = input("Введите ID получателя: ")
            amount = int(input("Введите сумму в копейках: "))
            create_transaction(stub, user, receiver, amount)

        elif choice == "3":
            txn_id = input("Введите ID транзакции: ")
            verify_transaction(stub, txn_id)

        else:
            print("Неверный выбор.")


if __name__ == '__main__':
    run()