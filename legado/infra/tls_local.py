# =============================================================================
# infra/tls_local.py
#
# Certificado TLS autofirmado para el servidor de sincronización local
# (ecosistema móvil). Genera/persiste un par cert+clave y expone su huella
# SHA-256 para emparejamiento TOFU (Trust On First Use): el QR lleva la huella
# y el cliente móvil la fija; en conexiones posteriores valida el certificado
# por huella (no por CA), logrando confidencialidad y mitigación de MitM en la
# LAN sin depender de una autoridad certificadora ni del entorno.
#
# El certificado se PERSISTE (config del usuario) para que la huella sea
# ESTABLE entre reinicios del PC — así el dispositivo ya emparejado sigue
# confiando sin re-escanear. Se regenera solo si falta o está corrupto/expirado.
#
# Requiere `cryptography`. Si no está disponible, el llamador degrada a HTTP
# plano (LAN + token); ver servicios/servidor_sync.py.
# =============================================================================

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from infra.logger import obtener_logger

_log = obtener_logger("tls_local")

NOMBRE_CERT = "sync_cert.pem"
NOMBRE_CLAVE = "sync_key.pem"
# Vida larga: evita expiraciones que romperían el TOFU. La huella es lo que
# ancla la confianza, no la fecha.
DIAS_VALIDEZ = 3650


def cryptography_disponible() -> bool:
    return importlib.util.find_spec("cryptography") is not None


@dataclass(frozen=True)
class CertificadoTLS:
    cert_path: Path
    key_path: Path
    fingerprint_sha256: str  # hex en minúsculas, sin separadores


def huella_sha256_pem(cert_path: Path) -> Optional[str]:
    """SHA-256 (hex) del certificado DER derivado del PEM, o None si falla."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        data = Path(cert_path).read_bytes()
        cert = x509.load_pem_x509_certificate(data)
        der = cert.public_bytes(serialization.Encoding.DER)
        return hashlib.sha256(der).hexdigest()
    except Exception as exc:
        _log.debug("No se pudo calcular la huella del certificado: %s", exc)
        return None


def _cert_vigente(cert_path: Path) -> bool:
    try:
        from cryptography import x509

        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        ahora = datetime.datetime.now(datetime.timezone.utc)
        # `not_valid_after_utc` está disponible en cryptography modernas; con
        # fallback al naive para versiones antiguas.
        try:
            no_despues = cert.not_valid_after_utc
        except AttributeError:
            no_despues = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        return no_despues > ahora
    except Exception:
        return False


def _generar(cert_path: Path, key_path: Path, ips: Iterable[str]) -> None:
    """Genera un cert autofirmado EC (P-256) con SAN de IPs/hosts locales."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    clave = ec.generate_private_key(ec.SECP256R1())

    nombre = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "NB Sound Sync"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NBSOUND"),
    ])

    # SAN: localhost + loopback + las IPs LAN conocidas. El cliente valida por
    # HUELLA (TOFU), no por hostname, así que un cambio de IP no rompe nada.
    sans: list = [x509.DNSName("localhost"), x509.DNSName("nbsound.local")]
    vistas: set[str] = set()
    for ip in list(ips) + ["127.0.0.1", "::1"]:
        ip = (ip or "").strip()
        if not ip or ip in vistas:
            continue
        vistas.add(ip)
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue

    ahora = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(minutes=5))
        .not_valid_after(ahora + datetime.timedelta(days=DIAS_VALIDEZ))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(clave, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        clave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    # Permisos restrictivos para la clave privada (best-effort; no aplica en Win).
    try:
        key_path.chmod(0o600)
    except OSError:
        pass


def obtener_o_crear_certificado(
    dir_certificados: Path, ips_lan: Optional[Iterable[str]] = None
) -> Optional[CertificadoTLS]:
    """Devuelve el certificado TLS (creándolo si falta/expiró), o None si no
    está disponible `cryptography`.

    Reusa el certificado persistido para mantener una huella ESTABLE entre
    reinicios (clave del modelo TOFU del cliente).
    """
    if not cryptography_disponible():
        return None
    dir_certificados = Path(dir_certificados)
    cert_path = dir_certificados / NOMBRE_CERT
    key_path = dir_certificados / NOMBRE_CLAVE

    necesita_generar = not (cert_path.is_file() and key_path.is_file()) or not _cert_vigente(cert_path)
    if necesita_generar:
        try:
            _generar(cert_path, key_path, list(ips_lan or []))
            _log.info("Certificado TLS de sincronización generado en %s", cert_path)
        except Exception as exc:
            _log.warning("No se pudo generar el certificado TLS: %s", exc)
            return None

    fingerprint = huella_sha256_pem(cert_path)
    if not fingerprint:
        return None
    return CertificadoTLS(cert_path=cert_path, key_path=key_path, fingerprint_sha256=fingerprint)
