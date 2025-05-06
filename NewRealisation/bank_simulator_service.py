# bank_simulator_service.py
from concurrent import futures
import grpc
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
from bank_simulator import BankSimulator

class BankVerificationService(pb2_grpc.BankVerificationServicer):
    def __init__(self):
        self.bank_simulator = BankSimulator()

    def ValidateHold(self, request, context):
        print(f"[ValidateHold] Проверка холда: {request.amount_cents / 100} руб.")
        result = self.bank_simulator.validate_hold(request.amount_cents)
        return pb2.HoldResponse(
            success=result["success"],
            time_taken_sec=result["time_taken_sec"]
        )

    def ProcessPayment(self, request, context):
        print(f"[ProcessPayment] Обработка платежа: {request.amount_cents / 100} руб.")
        result = self.bank_simulator.process_payment(request.amount_cents)
        return pb2.PaymentResponse(
            success=result["success"],
            time_taken_sec=result["time_taken_sec"],
            timestamp=result["timestamp"]
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_BankVerificationServicer_to_server(BankVerificationService(), server)
    server.add_insecure_port('[::]:50052')
    print("🏦 Банковский gRPC-сервер запущен на порту 50052...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()