import time

class MockVideoService:
    def __init__(self, price_per_second=0.01):  # 1 копейка за секунду
        self.price_per_second = price_per_second
        self.duration = 0

    def start_streaming(self, duration_seconds):
        print("Начало просмотра...")
        for sec in range(duration_seconds):
            self.duration += 1
            time.sleep(1)
            yield self.price_per_second

    def get_total_cost(self):
        return round(self.duration * self.price_per_second, 2)

if __name__ == '__main__':
    service = MockVideoService(price_per_second=0.01)
    for _ in service.start_streaming(10):
        print(f"Оплачено {service.price_per_second} руб. за {service.duration} сек.")
    print("Итого:", service.get_total_cost(), "руб.")