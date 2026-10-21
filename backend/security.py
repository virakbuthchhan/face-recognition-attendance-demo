import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
from urllib.parse import urlsplit


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(value):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600_000).hex()


def verify_password(value, encoded):
    salt, expected = encoded.split(':')
    actual = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600_000).hex()
    return hmac.compare_digest(actual, expected)


def signature(secret, timestamp, body):
    return hmac.new(secret.encode(), str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()


def validate_destination(url):
    parsed = urlsplit(url)
    allowed = {s.strip().lower() for s in os.getenv('WEBHOOK_ALLOWED_HOSTS', '').split(',') if s.strip()}
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.hostname.lower() not in allowed
            or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError('Webhook requires HTTPS port 443 and an operator-allowlisted hostname')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Webhook must resolve exclusively to public addresses')
