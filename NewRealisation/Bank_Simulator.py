import time
import random

class BankSimulator:
    def __init__(self):
        self.min_delay = 0.005  # минимальная задержка
        self.max_delay = 0.020  # максимальная задержка

    def verify_hold(self, amount_kopecks):
        # Эмуляция проверки холда в банке отправителя
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
        return True, delay

    def notify_recipient_bank(self, amount_kopecks):
        # Эмуляция связи с банком-получателем
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
        return True, delay
