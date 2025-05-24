# bank_simulator.py
import time
import jwt
import random

JWT_SECRET = "your-secret-key"
JWT_ALGORITHM = "HS256"


class BankAccount:
    def __init__(self, balance_rubles=0.0):
        self.balance = int(balance_rubles * 100)  # храним в копейках
        self.holded = 0

    def get_balance(self):
        return self.balance / 100.0  # возвращаем в рублях

    def charge_from_hold(self, amount_rubles):
        amount_kopecks = int(amount_rubles * 100)
        if self.balance >= amount_kopecks:
            self.balance -= amount_kopecks
            self.holded += amount_kopecks
            return True
        return False

    def release_hold(self, amount_rubles):
        amount_kopecks = int(amount_rubles * 100)
        if self.holded >= amount_kopecks:
            self.holded -= amount_kopecks
            return True
        return False

class RecipientAccount:
    def __init__(self):
        self.received = 0

    def credit(self, amount_kopecks):
        self.received += amount_kopecks

    def __repr__(self):
        return f"<RecipientAccount received={self.received}>"


def simulate_internal_check():
    # Имитация обработки внутри банка (например, AML или другие проверки)
    time.sleep(random.uniform(0.01, 0.05))


def generate_jwt(user_id):
    payload = {
        "user_id": user_id,
        "timestamp": int(time.time())
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
