from Service import MockVideoService
from Bank_Simulator import BankSimulator

class PaymentEngine:
    def __init__(self, service, bank):
        self.service = service
        self.bank = bank

    def start_session(self, initial_hold=50):
        if not self.bank.hold(initial_hold):
            raise Exception("Не удалось установить холд")

        print("Сессия начата")
        for cost in self.service.start_streaming(10):
            if self.bank.hold_amount < initial_hold * 0.3:
                print("Дополнительный холд")
                self.bank.hold(initial_hold)
            self.bank.charge(cost)

        total = self.service.get_total_cost()
        self.bank.release_hold()
        print(f"Итого оплачено: {total} руб.")


video_service = MockVideoService(price_per_second=0.01)
bank = BankSimulator(balance=200)
engine = PaymentEngine(video_service, bank)
engine.start_session(initial_hold=50)