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
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "My CA")])
    ca_cert = x509.CertificateBuilder().subject_name(ca_subject).issuer_name(ca_subject).public_key(
        ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.now(timezone.utc)).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256(), default_backend())

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    server_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = x509.CertificateBuilder().subject_name(server_subject).issuer_name(ca_subject).public_key(
        server_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.now(timezone.utc)).not_valid_after(
        datetime.now(timezone.utc) + timedelta(days=365)).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False).add_extension(
        x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False).sign(ca_key, hashes.SHA256(), default_backend())

    with open("ca.crt", "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open("server.key", "wb") as f:
        f.write(server_key.private_bytes(encoding=serialization.Encoding.PEM,
                                         format=serialization.PrivateFormat.TraditionalOpenSSL,
                                         encryption_algorithm=serialization.NoEncryption()))
    with open("server.crt", "wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))

if not all(os.path.exists(f) for f in ["cert.pem", "key.pem", "ca.crt", "server.crt", "server.key"]):
    print("🔄 Сертификаты отсутствуют — начинаем генерацию...")
    generate_self_signed_cert()
    generate_grpc_certs()
    print("✅ Все сертификаты успешно созданы!")

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.urandom(32)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
Talisman(app, force_https=True, content_security_policy=None)
csrf = CSRFProtect(app)

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

class BankAccount:
    def __init__(self, user_id, initial_balance_kopecks):
        self.user_id = user_id
        self.balance = initial_balance_kopecks
        self.current_hold_total = 0
        self.current_hold_used = 0
        self.next_hold_total = 0
        self.lock = threading.Lock()
        self.hold_history_log = []

    def get_balance(self):
        with self.lock:
            return self.balance / 100

    def _secure_hold_from_balance(self, amount_kopecks):
        if self.balance >= amount_kopecks:
            self.balance -= amount_kopecks
            return True
        return False

    def make_hold(self, amount_kopecks):
        op_start_time = time.perf_counter()
        log_entry = {"start_time_str": datetime.now().isoformat(), "status": "initiated"}
        success_status = False
        with self.lock:
            if self.current_hold_total == 0:
                if self._secure_hold_from_balance(amount_kopecks):
                    self.current_hold_total = amount_kopecks
                    self.current_hold_used = 0
                    log_entry["status"] = f"Первичный холд установлен: {amount_kopecks / 100} руб."
                    success_status = True
                else:
                    log_entry["status"] = "Недостаточно средств для первичного холда"
            elif self.next_hold_total == 0:
                if self._secure_hold_from_balance(amount_kopecks):
                    self.next_hold_total = amount_kopecks
                    log_entry["status"] = f"Следующий холд зарезервирован: {amount_kopecks / 100} руб."
                    success_status = True
                else:
                    log_entry["status"] = "Недостаточно средств для резервирования следующего холда"
            else:
                log_entry["status"] = "Текущий и следующий холд уже установлены"
                success_status = True
        
        op_end_time = time.perf_counter()
        duration_ms = (op_end_time - op_start_time) * 1000
        log_entry["end_time_str"] = datetime.now().isoformat()
        log_entry["duration_ms"] = round(duration_ms, 2)
        print(f"{log_entry['status']}. Время: {duration_ms:.2f} мс.")
        self.hold_history_log.append(log_entry)
        return success_status

    def charge_from_hold(self, amount_kopecks):
        with self.lock:
            if self.current_hold_total > 0 and (self.current_hold_used + amount_kopecks <= self.current_hold_total):
                self.current_hold_used += amount_kopecks
                return True
            return False

    def switch_to_next_hold(self):
        with self.lock:
            if self.next_hold_total > 0:
                self.current_hold_total = self.next_hold_total
                self.current_hold_used = 0
                self.next_hold_total = 0
                print(f"🔄 Переключение на следующий холд. Новый активный холд: {self.current_hold_total / 100} руб.")
                return True
            return False

    def release_all_holds(self):
        with self.lock:
            released_amount = 0
            if self.current_hold_total > 0:
                released_amount += (self.current_hold_total - self.current_hold_used)
                self.current_hold_total = 0
                self.current_hold_used = 0
            if self.next_hold_total > 0:
                released_amount += self.next_hold_total
                self.next_hold_total = 0
            self.balance += released_amount
            if released_amount > 0:
                print(f"🔓 Все холды освобождены. Возвращено на баланс: {released_amount / 100} руб.")
            self.hold_history_log.clear()
            return released_amount

    def get_current_hold_total(self):
        with self.lock:
            return self.current_hold_total / 100

    def get_current_hold_used(self):
        with self.lock:
            return self.current_hold_used / 100
            
    def get_current_hold_remaining(self):
        with self.lock:
            return (self.current_hold_total - self.current_hold_used) / 100

    def get_next_hold_total(self):
        with self.lock:
            return self.next_hold_total / 100

    def get_overall_hold_secured(self):
        with self.lock:
            return (self.current_hold_total + self.next_hold_total) / 100

bank_account = BankAccount(user_id="user1", initial_balance_kopecks=1000000)
stub = None
session_id = ""
stop_streaming = threading.Event()
real_time_data = {"used": 0.0, "balance": bank_account.get_balance()}
payment_times_log = []
session_start_time = None
session_end_time = None # Added to store session end time

def connect_to_grpc():
    global stub
    try:
        with open("ca.crt", "rb") as f:
            trusted_certs = f.read()
        credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)
        channel = grpc.secure_channel("localhost:50051", credentials, options=[
            ("grpc.ssl_target_name_override", "localhost"),
            ("grpc.default_authority", "localhost")
        ])
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = pb2_grpc.MicroPaymentServiceStub(channel)
        print("✅ Успешное подключение к gRPC серверу через TLS")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к gRPC: {e}")
        stub = None
        return False

def streaming_process(session_id_arg):
    global real_time_data, payment_times_log
    base_payment_kopecks = 10
    default_hold_chunk_kopecks = 10000

    if bank_account.current_hold_total == 0:
        print("ℹ️ Запрос на установку первичного холда...")
        if not bank_account.make_hold(default_hold_chunk_kopecks):
            print("❌ Не удалось установить первичный холд. Сессия не начнется.")
            stop_streaming.set()
            return

    while not stop_streaming.is_set():
        with bank_account.lock:
            current_hold_total_kopecks_val = bank_account.current_hold_total
            current_hold_used_kopecks_val = bank_account.current_hold_used
            next_hold_total_kopecks_val = bank_account.next_hold_total
        
        needs_new_hold_threshold = current_hold_total_kopecks_val * 2 / 3

        if current_hold_total_kopecks_val > 0 and current_hold_used_kopecks_val >= current_hold_total_kopecks_val:
            print(f"🔔 Текущий холд ({current_hold_total_kopecks_val/100} руб.) исчерпан.")
            if bank_account.switch_to_next_hold():
                with bank_account.lock:
                    current_hold_total_kopecks_val = bank_account.current_hold_total
                    current_hold_used_kopecks_val = bank_account.current_hold_used
                    next_hold_total_kopecks_val = bank_account.next_hold_total
                needs_new_hold_threshold = current_hold_total_kopecks_val * 2 / 3
            else:
                print("🚫 Текущий холд исчерпан, следующего холда нет. Остановка.")
                stop_streaming.set()
                break

        if current_hold_total_kopecks_val > 0 and \
           current_hold_used_kopecks_val >= needs_new_hold_threshold and \
           next_hold_total_kopecks_val == 0:
            print(f"🔔 Использовано {current_hold_used_kopecks_val/100:.2f} из {current_hold_total_kopecks_val/100:.2f} текущего холда. Запрос на следующий холд...")
            bank_account.make_hold(default_hold_chunk_kopecks)
            with bank_account.lock:
                 next_hold_total_kopecks_val = bank_account.next_hold_total

        if bank_account.charge_from_hold(base_payment_kopecks):
            real_time_data["used"] += base_payment_kopecks / 100 
            real_time_data["balance"] = bank_account.get_balance()
            
            frame_send_start_time_perf = None 
            try:
                metadata = [("authorization", f"Bearer {session_id_arg}")]
                payment_request_iter = iter([pb2.PaymentRequest(session_id=session_id_arg, amount_cents=base_payment_kopecks)])
                frame_send_start_time_perf = time.perf_counter()
                stub.StreamPayments(payment_request_iter, metadata=metadata)
                frame_send_end_time_perf = time.perf_counter()
                frame_send_duration_ms = (frame_send_end_time_perf - frame_send_start_time_perf) * 1000
                payment_times_log.append(frame_send_duration_ms)
                with bank_account.lock:
                    ch_used_rub = bank_account.current_hold_used / 100
                    ch_rem_rub = (bank_account.current_hold_total - bank_account.current_hold_used) / 100
                    nh_rub = bank_account.next_hold_total / 100
                print(f"💸 Кадр ({base_payment_kopecks / 100} руб.) отправлен. Время: {frame_send_duration_ms:.2f} мс. "
                      f"Исп. тек. холд: {ch_used_rub:.2f}. Остаток тек. холда: {ch_rem_rub:.2f}. След. холд: {nh_rub:.2f} руб. "
                      f"Всего за сессию: {real_time_data['used']:.2f} руб.")
            except Exception as e:
                error_duration_msg = ""
                if frame_send_start_time_perf is not None:
                    frame_send_end_time_on_error = time.perf_counter()
                    duration_on_error_ms = (frame_send_end_time_on_error - frame_send_start_time_perf) * 1000
                    error_duration_msg = f" Время до ошибки: {duration_on_error_ms:.2f} мс."
                print(f"❌ Ошибка отправки gRPC:{error_duration_msg} Ошибка: {e}")
                stop_streaming.set()
                break
        else:
            if not stop_streaming.is_set():
                with bank_account.lock:
                    ch_used_rub_fail = bank_account.current_hold_used / 100
                    ch_rem_rub_fail = (bank_account.current_hold_total - bank_account.current_hold_used) / 100
                print(f"🚫 Недостаточно средств в текущем холде для платежа ({base_payment_kopecks/100} руб.). "
                    f"Исп: {ch_used_rub_fail:.2f}, Остаток: {ch_rem_rub_fail:.2f}. Остановка.")
                stop_streaming.set()
            break
        time.sleep(0.005)

    print("🏁 Сессия завершена.")
    bank_account.release_all_holds()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
@auth_required
@csrf.exempt
def start_session_route():
    global session_id, stop_streaming, real_time_data, session_start_time, session_end_time, payment_times_log
    real_time_data["used"] = 0.0
    bank_account.release_all_holds()
    payment_times_log.clear()
    session_id = f"sess_{int(time.time())}"
    session_start_time = time.time()
    session_end_time = None # Reset session end time
    stop_streaming.clear()
    threading.Thread(target=streaming_process, args=(session_id,), daemon=True).start()
    return jsonify({"session_id": session_id})

@app.route("/stop", methods=["POST"])
@auth_required
@csrf.exempt
def stop_session():
    global session_end_time
    stop_streaming.set()
    session_end_time = time.time() # Record session end time
    return jsonify({"status": "stopped"})

@app.route("/status", methods=["GET"])
@auth_required
def status():
    global session_start_time, session_end_time, payment_times_log
    with bank_account.lock:
        current_hold_total_kopecks = bank_account.current_hold_total
        current_hold_used_kopecks = bank_account.current_hold_used
        next_hold_total_kopecks = bank_account.next_hold_total
        hold_history = list(bank_account.hold_history_log)

    needs_new_hold_check = False
    if current_hold_total_kopecks > 0 and next_hold_total_kopecks == 0:
        if current_hold_used_kopecks >= (current_hold_total_kopecks * 2 / 3):
            needs_new_hold_check = True

    session_duration_seconds = 0
    if session_start_time:
        # If session_end_time is set (session stopped), use it. Otherwise (session active), use current time.
        current_or_end_time = session_end_time if session_end_time else time.time()
        session_duration_seconds = current_or_end_time - session_start_time
        
    avg_hold_time_ms = 0
    if hold_history:
        valid_hold_durations = [h.get('duration_ms', 0) for h in hold_history if h.get('duration_ms') is not None]
        if valid_hold_durations:
            total_hold_time = sum(valid_hold_durations)
            avg_hold_time_ms = total_hold_time / len(valid_hold_durations)
        
    avg_payment_time_ms = 0
    if payment_times_log:
        avg_payment_time_ms = sum(payment_times_log) / len(payment_times_log)

    return jsonify({
        "balance": round(bank_account.get_balance(), 2),
        "current_active_hold": {
            "total": round(bank_account.get_current_hold_total(), 2),
            "used": round(bank_account.get_current_hold_used(), 2),
            "remaining": round(bank_account.get_current_hold_remaining(), 2)
        },
        "next_pending_hold": round(bank_account.get_next_hold_total(), 2),
        "overall_secured_by_holds": round(bank_account.get_overall_hold_secured(), 2),
        "needs_to_secure_next_hold": needs_new_hold_check,
        "total_session_used": round(real_time_data["used"], 2),
        "session_duration_seconds": round(session_duration_seconds, 2),
        "avg_hold_request_time_ms": round(avg_hold_time_ms, 2),
        "avg_payment_time_ms": round(avg_payment_time_ms, 2),
        "hold_requests_history": hold_history,
        "is_session_active": not stop_streaming.is_set() # Added to help client side logic
    })

if __name__ == "__main__":
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("Created templates directory")
    if not os.path.exists("templates/index.html"):
        with open("templates/index.html", "w") as f_html:
            f_html.write("<h1>Placeholder - Will be replaced</h1>")
            print("Created dummy templates/index.html")

    if not connect_to_grpc():
        print("❌ Не удалось подключиться к gRPC серверу")
        exit(1)
    app.run(debug=False, port=5000, ssl_context=("cert.pem", "key.pem"), host="0.0.0.0", threaded=True)

