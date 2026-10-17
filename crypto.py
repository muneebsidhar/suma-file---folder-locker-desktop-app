import os
import hmac
import hashlib
import base64

PBKDF2_ROUNDS_V1 = 200_000
PBKDF2_ROUNDS_V2 = 600_000

CHUNK_SIZE = 1024 * 1024
FILE_MAGIC_V2 = b"SUMA2"


def hash_password(password, salt=None, ver_salt=None, iterations=PBKDF2_ROUNDS_V2):
    if salt is None:
        salt = os.urandom(16)
    if ver_salt is None:
        ver_salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    tag = hmac.new(dk, ver_salt, hashlib.sha256).hexdigest()
    return salt.hex(), ver_salt.hex(), tag, iterations


def verify_password(password, cfg):
    it = cfg.get("iter", PBKDF2_ROUNDS_V1)
    pw = password.encode("utf-8")
    if cfg.get("ver_salt"):
        dk = hashlib.pbkdf2_hmac("sha256", pw, bytes.fromhex(cfg["salt"]), it)
        tag = hmac.new(dk, bytes.fromhex(cfg["ver_salt"]), hashlib.sha256).hexdigest()
        return hmac.compare_digest(tag, cfg["hash"])
    dk = hashlib.pbkdf2_hmac("sha256", pw, bytes.fromhex(cfg["salt"]), it)
    return hmac.compare_digest(dk.hex(), cfg["hash"])


def needs_upgrade(cfg):
    return cfg.get("iter", PBKDF2_ROUNDS_V1) < PBKDF2_ROUNDS_V2 or not cfg.get("ver_salt")


def upgrade_hash(cfg, password):
    s, vs, tag, it = hash_password(password)
    cfg["salt"] = s
    cfg["ver_salt"] = vs
    cfg["hash"] = tag
    cfg["iter"] = it


def _kdf_fernet(secret, salt_hex):
    from cryptography.fernet import Fernet
    raw = hashlib.pbkdf2_hmac("sha256", secret, bytes.fromhex(salt_hex),
                              PBKDF2_ROUNDS_V1, dklen=32)
    return Fernet(base64.urlsafe_b64encode(raw))


def master_fernet(password, ksalt_hex):
    return _kdf_fernet(password.encode("utf-8"), ksalt_hex)


def rec_fernet(rec_key, salt_hex):
    return _kdf_fernet(rec_key, salt_hex)


def encrypt_file(src, dst, fernet):
    n = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(FILE_MAGIC_V2)
        fout.write(b"\x00" * 8)
        while True:
            chunk = fin.read(CHUNK_SIZE)
            if not chunk:
                break
            token = fernet.encrypt(n.to_bytes(8, "big") + chunk)
            fout.write(len(token).to_bytes(4, "big"))
            fout.write(token)
            n += 1
        fout.seek(len(FILE_MAGIC_V2))
        fout.write(n.to_bytes(8, "big"))


def decrypt_file(src, dst, fernet):
    with open(src, "rb") as fin:
        magic = fin.read(len(FILE_MAGIC_V2))
        if magic != FILE_MAGIC_V2:
            rest = fin.read()
            data = fernet.decrypt(magic + rest)
            with open(dst, "wb") as fout:
                fout.write(data)
            return "v1"
        _decrypt_v2(fin, dst, fernet)
        return "v2"


def _decrypt_v2(fin, dst, fernet):
    raw_count = fin.read(8)
    if len(raw_count) < 8:
        raise ValueError("truncated vault file (header)")
    count = int.from_bytes(raw_count, "big")
    with open(dst, "wb") as fout:
        for i in range(count):
            raw_len = fin.read(4)
            if len(raw_len) < 4:
                raise ValueError("truncated vault file (chunk length)")
            tlen = int.from_bytes(raw_len, "big")
            token = fin.read(tlen)
            if len(token) < tlen:
                raise ValueError("truncated vault file (chunk data)")
            plain = fernet.decrypt(token)
            idx = int.from_bytes(plain[:8], "big")
            if idx != i:
                raise ValueError("chunk order mismatch — file may be tampered")
            fout.write(plain[8:])
