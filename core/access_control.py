import hmac
import os
from collections.abc import Mapping
from typing import Any


ACCESS_CODE_ENV = "EU_FUNDING_ACCESS_CODE"
ACCESS_CODE_SECRET_KEYS = ("access_code", "EU_FUNDING_ACCESS_CODE")


def _read_secret(secrets: Mapping[str, Any] | None, key: str) -> str:
    if secrets is None:
        return ""
    try:
        value = secrets.get(key, "")
    except Exception:
        return ""
    return str(value or "").strip()


def get_configured_access_code(
    *,
    env: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
) -> str:
    """Return the configured access code without defining a hard-coded fallback."""
    environment = env if env is not None else os.environ
    env_value = str(environment.get(ACCESS_CODE_ENV, "") or "").strip()
    if env_value:
        return env_value

    for key in ACCESS_CODE_SECRET_KEYS:
        secret_value = _read_secret(secrets, key)
        if secret_value:
            return secret_value
    return ""


def access_gate_required(
    *,
    env: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
) -> bool:
    return bool(get_configured_access_code(env=env, secrets=secrets))


def verify_access_code(submitted_code: str, configured_code: str) -> bool:
    submitted = str(submitted_code or "").strip()
    configured = str(configured_code or "").strip()
    if not submitted or not configured:
        return False
    return hmac.compare_digest(submitted, configured)
