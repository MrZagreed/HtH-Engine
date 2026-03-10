import hashlib
from typing import Dict, Any

from .logging_setup import log

PROJECT_NAME = "HtH Engine"
AUTHOR_NAME = "Mr.Zagreed"
AUTHOR_NOTICE = "Discord Karaoke RPC by Mr.Zagreed"
AUTHORSHIP_PROOF_SHA256 = "55377ad467bf8e74665cb5ea2bb5ecea9079cf010cf19b4d0d09082f33b9d230"


def _proof_payload() -> str:
    return f"{PROJECT_NAME}|{AUTHOR_NOTICE}|{AUTHOR_NAME}"


def verify_authorship_proof() -> bool:
    digest = hashlib.sha256(_proof_payload().encode("utf-8")).hexdigest()
    return digest == AUTHORSHIP_PROOF_SHA256


def enforce_authorship(config: Dict[str, Any]) -> None:
    """Tamper-evident runtime authorship enforcement.

    Note: this does not make modification impossible, but ensures attribution is
    automatically restored in standard runtime flow and tampering is logged.
    """
    configured_hover = str(config.get("discord_hover_text", "")).strip()
    if configured_hover != AUTHOR_NOTICE:
        log(
            "Authorship notice mismatch detected in config; restoring official author attribution",
            "WARNING",
            "license",
        )
        config["discord_hover_text"] = AUTHOR_NOTICE

    config["project_author"] = AUTHOR_NAME
    config["project_name"] = PROJECT_NAME
    config["authorship_proof"] = AUTHORSHIP_PROOF_SHA256[:16]

    if not verify_authorship_proof():
        log("Authorship proof validation failed: code integrity check mismatch", "ERROR", "license")
    else:
        log(f"Authorship proof OK: {AUTHORSHIP_PROOF_SHA256[:12]}...", "DEBUG", "license")


__all__ = [
    "PROJECT_NAME",
    "AUTHOR_NAME",
    "AUTHOR_NOTICE",
    "AUTHORSHIP_PROOF_SHA256",
    "verify_authorship_proof",
    "enforce_authorship",
]

