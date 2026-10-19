"""Certificates: create a self-signed digital ID, sign with a certificate, validate signatures."""

from __future__ import annotations

import datetime as dt
import io

import pymupdf as fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from . import Ctx, OpResult, op, page_list


def create_digital_id(name: str, email: str, organization: str, passphrase: str,
                      years: int = 5) -> bytes:
    """Return a PKCS#12 (.p12) file holding a new self-signed signing certificate."""
    if not name.strip() or not passphrase:
        raise ValueError("Name and passphrase are required")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
    if organization:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=365 * years))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                                         key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=False, crl_sign=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        name.encode(), key, cert, None,
        serialization.BestAvailableEncryption(passphrase.encode()))


@op("sign_certificate", "certificates", "Digitally sign with a .p12/.pfx digital ID (visible or invisible)")
def sign_certificate(doc: fitz.Document, ctx: Ctx, blob_id: str, passphrase: str,
                     page: int = 0, rect: list[float] | None = None, reason: str = "",
                     location: str = "", field_name: str | None = None):
    if ctx.entry.is_encrypted():
        raise ValueError("Remove the password before certificate signing")
    page_list(doc, [page])
    _name, p12 = ctx.blob(blob_id)
    try:
        signer = signers.SimpleSigner.load_pkcs12_data(p12, other_certs=[],
                                                       passphrase=passphrase.encode())
    except Exception as exc:
        raise ValueError(f"Could not open the digital ID: {exc}") from exc
    if signer is None:
        raise ValueError("Could not open the digital ID (wrong passphrase?)")
    existing = {w.field_name for p in doc for w in p.widgets()}
    name = field_name or next(f"Signature{i}" for i in range(1, 999) if f"Signature{i}" not in existing)
    box = None
    if rect is not None:
        # pyHanko expects PDF user space (y up), which is what the UI sends.
        if len(rect) != 4:
            raise ValueError("rect needs four numbers")
        r = fitz.Rect(rect).normalize()
        box = (int(r.x0), int(r.y0), int(r.x1), int(r.y1))
    writer = IncrementalPdfFileWriter(io.BytesIO(ctx.entry.data), strict=False)
    if name not in existing:
        fields.append_signature_field(writer, fields.SigFieldSpec(name, on_page=page, box=box))
    meta = signers.PdfSignatureMetadata(field_name=name, reason=reason or None,
                                        location=location or None)
    out = signers.sign_pdf(writer, meta, signer=signer)
    return OpResult(replace_bytes=out.getvalue(), data={"field": name})


def validate_signatures(data: bytes) -> list[dict]:
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    results = []
    for sig in reader.embedded_regular_signatures:
        status = validate_pdf_signature(sig, ValidationContext(allow_fetching=False))
        cert = status.signing_cert
        results.append({
            "field": sig.field_name,
            "signer": cert.subject.human_friendly if cert else None,
            "signed_at": sig.self_reported_timestamp.isoformat() if sig.self_reported_timestamp else None,
            "intact": status.intact,
            "valid": status.valid,
            "trusted": status.trusted,
            "covers_whole_document": status.coverage.name == "ENTIRE_FILE",
            "modification_level": status.modification_level.name if status.modification_level else None,
            "summary": status.summary(),
        })
    return results
