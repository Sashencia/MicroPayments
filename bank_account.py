class BankAccount:
    def __init__(self, user_id, initial_balance=1000.0):
        """
        Инициализация банковского счета.
        :param user_id: Идентификатор пользователя.
        :param initial_balance: Начальный баланс счета (по умолчанию 1000.0 рублей).
        """
        self.user_id = user_id
        self.balance = initial_balance

    def withdraw(self, amount):
        """
        Снятие средств со счета.
        :param amount: Сумма для снятия.
        :return: True, если снятие прошло успешно, иначе False.
        """
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
        """
        Получение текущего баланса счета.
        :return: Текущий баланс.
        """
        return self.balance

    def __str__(self):
        return f"BankAccount(user_id={self.user_id}, balance={self.balance:.2f} RUB)"