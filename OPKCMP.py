class OPKCMP:
    def __init__(self):
        self.buffer = []  # Буфер для хранения пакетов
        self.final_packet_received = False  # Флаг получения финального пакета
        self.final_balance = 0.0  # Итоговый баланс для отправки получателю

    def add_packet(self, packet):
        """Добавляет пакет в буфер."""
        self.buffer.append(packet)
        print(f"ОПКЦ МП: Пакет добавлен в буфер. Время: {packet['time']}, Литры: {packet['liters']}, Баланс: {packet['balance']}")

    def process_final_packet(self):
        """Обрабатывает финальный пакет и вычисляет итоговый баланс."""
        if self.buffer:
            self.final_packet_received = True
            final_packet = self.buffer[-1]  # Последний пакет
            self.final_balance = final_packet["balance"]
            print(f"ОПКЦ МП: Получен финальный пакет. Итоговый баланс: {self.final_balance} RUB")

    def send_final_balance_to_recipient(self, recipient_account):
        """Отправляет итоговый баланс на счет получателя."""
        if self.final_packet_received:
            recipient_account.deposit(self.final_balance)
            print(f"ОПКЦ МП: Итоговый баланс {self.final_balance} RUB отправлен на счет получателя.")
            self.buffer.clear()  # Очищаем буфер
            self.final_packet_received = False