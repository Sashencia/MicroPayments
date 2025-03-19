from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_keys(user_id):
    # Генерация закрытого ключа
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    # Сохранение закрытого ключа в файл
    with open(f"{user_id}_private.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    # Генерация открытого ключа
    public_key = private_key.public_key()
    # Сохранение открытого ключа в файл
    with open(f"{user_id}_public.pem", "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

if __name__ == '__main__':
    generate_keys("user1")
    generate_keys("user2")