import os
class BankAccount:
    def __init__(self, user_id, initial_balance=1000000.0):
        self.user_id = user_id
        self.balance = initial_balance

    def withdraw(self, amount):
        if amount <= 0:
            print(f"Invalid amount: {amount}. Amount must be positive.")
            return False
        if self.balance >= amount:
            self.balance -= amount
            print(f"Withdrawal successful: {amount:.2f} RUB deducted. New balance: {self.balance:.2f} RUB")
            return True
        else:
            print(f"Insufficient funds. Required: {amount:.2f} RUB, Available: {self.balance:.2f} RUB")
            return False

    def get_balance(self):
        return self.balance

    def _save_balance(self):
        """
        Сохраняет текущий баланс в файл.
        """
        with open(self.balance_file, "w") as file:
            file.write(f"{self.balance:.2f}")

    def __str__(self):
        return f"BankAccount(user_id={self.user_id}, balance={self.balance:.2f} RUB)"