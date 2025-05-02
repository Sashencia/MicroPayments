class BankSimulator:
    def __init__(self, balance=1000):
        self.balance = balance
        self.hold_amount = 0

    def hold(self, amount):
        if self.balance >= amount:
            self.hold_amount = amount
            self.balance -= amount
            print(f"Холд {amount} руб. установлен")
            return True
        else:
            print("Недостаточно средств для холда")
            return False

    def charge(self, amount):
        if amount <= self.hold_amount:
            print(f"Списано {amount} руб.")
            self.hold_amount -= amount
            return True
        else:
            print("Ошибка списания")
            return False

    def release_hold(self):
        self.balance += self.hold_amount
        print(f"Освобождено {self.hold_amount} руб.")
        self.hold_amount = 0

if __name__ == '__main__':
    bank = BankSimulator(balance=100)
    bank.hold(50)
    bank.charge(30)
    bank.release_hold()
    print("Баланс:", bank.balance)