from flask import Flask, render_template, jsonify, request
import grpc
import threading
import time
import micro_payment_pb2 as pb2
import micro_payment_pb2_grpc as pb2_grpc
from functools import wraps
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from datetime import datetime, timezone, timedelta
import os

# === Генерация самоподписанного SSL-сертификата для Flask ===
def generate_self_signed_cert():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Company"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        private_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.now(timezone.utc)).not_valid_after(datetime.now(timezone.utc) + timedelta(days=365)).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False).sign(private_key, hashes.SHA256(),
                                                                                      default_backend())
    with open("key.pem", "wb") as f:
        f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                          format=serialization.PrivateFormat.TraditionalOpenSSL,
                                          encryption_algorithm=serialization.NoEncryption()))
    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

# === Генерация gRPC-сертификатов ===
def generate_grpc_certs():
    # Генерация CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "My CA")])
    ca_cert = x509.CertificateBuilder().subject_name(ca_subject).issuer_name(ca_subject).public_key(
        ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.now(timezone.utc)).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256(),
                                                                             default_backend())

    # Серверный сертификат
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    server_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = x509.CertificateBuilder().subject_name(server_subject).issuer_name(ca_subject).public_key(
        server_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.now(timezone.utc)).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False).add_extension(
        x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False).sign(ca_key, hashes.SHA256(),
                                                                            default_backend())

    with open("ca.crt", "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open("server.key", "wb") as f:
        f.write(server_key.private_bytes(encoding=serialization.Encoding.PEM,
                                         format=serialization.PrivateFormat.TraditionalOpenSSL,
                                         encryption_algorithm=serialization.NoEncryption()))
    with open("server.crt", "wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))


# === Проверка наличия сертификатов ===
if not all(os.path.exists(f) for f in ["cert.pem", "key.pem", "ca.crt", "server.crt", "server.key"]):
    print("🔄 Сертификаты отсутствуют — начинаем генерацию...")
    generate_self_signed_cert()
    generate_grpc_certs()
    print("✅ Все сертификаты успешно созданы!")

# === Инициализация Flask ===
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

Talisman(app, force_https=True, content_security_policy=None)
csrf = CSRFProtect(app)

# === Модель данных ===
USERS = {"admin": "securepassword123"}

def check_auth(username, password):
    return USERS.get(username) == password

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# === Банковский аккаунт ===
class BankAccount:
    def __init__(self, user_id, initial_balance_kopecks):
        self.user_id = user_id
        self.balance = initial_balance_kopecks
        self.hold = 0
        self.used_hold = 0
        self.lock = threading.Lock()

    def get_balance(self):
        with self.lock:
            return self.balance / 100

    def make_hold(self, amount_kopecks):
        with self.lock:
            if self.balance >= amount_kopecks:
                self.hold += amount_kopecks
                self.balance -= amount_kopecks
                self.used_hold = 0
                print(f"✅ Холд установлен: {amount_kopecks / 100} руб.")
                return True
            else:
                print("❌ Недостаточно средств для холда")
                return False

    def charge_from_hold(self, amount_kopecks):
        with self.lock:
            if self.used_hold + amount_kopecks > self.hold:
                return False
            self.used_hold += amount_kopecks
            return True

    def release_hold(self):
        with self.lock:
            released = self.hold - self.used_hold
            self.balance += released
            print(f"🔓 Разморожено: {released / 100} руб.")
            self.hold = 0
            self.used_hold = 0
            return released

    def get_total_hold(self):
        return self.hold / 100

    def get_used_hold(self):
        return self.used_hold / 100

    def get_remaining_hold(self):
        return (self.hold - self.used_hold) / 100


# === Переменные состояния ===
bank_account = BankAccount(user_id="user1", initial_balance_kopecks=1000000)  # 10000 рублей
stub = None
session_id = ""
stop_streaming = threading.Event()
real_time_data = {"used": 0.0, "balance": bank_account.get_balance()}

# === Подключение к gRPC ===
def connect_to_grpc():
    global stub
    try:
        with open("ca.crt", "rb") as f:
            trusted_certs = f.read()

        credentials = grpc.ssl_channel_credentials(
            root_certificates=trusted_certs
        )

        channel = grpc.secure_channel(
            'localhost:50051',
            credentials,
            options=[
                ('grpc.ssl_target_name_override', 'localhost'),
                ('grpc.default_authority', 'localhost')
            ]
        )

        grpc.channel_ready_future(channel).result(timeout=10)
        stub = pb2_grpc.MicroPaymentServiceStub(channel)
        print("✅ Успешное подключение к gRPC серверу через TLS")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к gRPC: {e}")
        stub = None
        return False


# === Обработка потока платежей ===
def streaming_process(session_id):
    global total_used, real_time_data
    base_amount_kopecks = 10
    hold_amount_kopecks = 10000

    if bank_account.hold == 0:
        success = bank_account.make_hold(hold_amount_kopecks)
        if not success:
            stop_streaming.set()
            return

    while not stop_streaming.is_set():
        if bank_account.get_used_hold() >= bank_account.get_total_hold() * 2 / 3:
            print("🔔 Требуется новый холд")
            bank_account.release_hold()
            bank_account.make_hold(hold_amount_kopecks)

        if bank_account.charge_from_hold(base_amount_kopecks):
            real_time_data["used"] += base_amount_kopecks / 100
            real_time_data["balance"] = bank_account.get_balance()
            print(f"💸 Отправлено: {base_amount_kopecks / 100} руб. Осталось в холде: {bank_account.get_remaining_hold()} руб.")

            try:
                metadata = [('authorization', f'Bearer {session_id}')]
                stub.StreamPayments(iter([pb2.PaymentRequest(session_id=session_id, amount_cents=base_amount_kopecks)]),
                                    metadata=metadata)
            except Exception as e:
                print("Ошибка отправки:", e)
                stop_streaming.set()
                break
        else:
            print("🚫 Недостаточно средств в холде")
            stop_streaming.set()
            break
        time.sleep(0.005)

    print("🏁 Сессия завершена. Остаток холда освобождён.")
    bank_account.release_hold()


# === API маршруты ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
@auth_required
@csrf.exempt
def start_session():
    global session_id, stop_streaming
    session_id = f"sess_{int(time.time())}"
    stop_streaming.clear()
    threading.Thread(target=streaming_process, args=(session_id,), daemon=True).start()
    return jsonify({"session_id": session_id})

@app.route('/stop', methods=['POST'])
@auth_required
@csrf.exempt
def stop_session():
    stop_streaming.set()
    return jsonify({"status": "stopped"})

@app.route('/status', methods=['GET'])
@auth_required
def status():
    return jsonify({
        "balance": round(bank_account.get_balance(), 2),
        "hold": round(bank_account.get_total_hold(), 2),
        "used": round(bank_account.get_used_hold(), 2),
        "remaining": round(bank_account.get_remaining_hold(), 2),
        "needs_new_hold": bank_account.get_used_hold() >= bank_account.get_total_hold() * 2 / 3,
        "total_used": round(real_time_data["used"], 2)
    })


# === Запуск приложения ===
if __name__ == '__main__':
    if not connect_to_grpc():
        print("❌ Не удалось подключиться к gRPC серверу")
        exit(1)
    app.run(
        debug=False,
        port=5000,
        ssl_context=('cert.pem', 'key.pem'),
        host='0.0.0.0',
        threaded=True
    )