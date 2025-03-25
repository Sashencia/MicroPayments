class RecipientAccount:
    def __init__(self, user_id, initial_balance):
        self.user_id = user_id
        self.balance = initial_balance

    def deposit(self, amount):
        """Пополняет баланс получателя."""
        self.balance += amount
        print(f"Счет получателя: Баланс пополнен на {amount} RUB. Новый баланс: {self.balance} RUB")

    def get_balance(self):
        return self.balance