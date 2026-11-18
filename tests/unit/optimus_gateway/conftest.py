import ssl
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import optimus_gateway.upstream_client as upstream_module


@pytest.fixture
def provider_server_tls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ssl.SSLContext]:
    """Trust only a per-test, ephemeral certificate on the provider's watched TLS path."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "opt-in test loopback")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=10))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )
    cert_path = tmp_path / "loopback.pem"
    key_path = tmp_path / "loopback.key"
    cert_path.write_bytes(cert)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cadata=cert.decode("ascii"))
    https_handler = upstream_module._WatchedHTTPSHandler
    monkeypatch.setattr(upstream_module, "_WatchedHTTPSHandler", lambda: https_handler(context=client_context))
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    upstream_module._watched_opener.cache_clear()
    try:
        yield server_context
    finally:
        upstream_module._watched_opener.cache_clear()
