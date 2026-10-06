"""Validasi X-Cron-Secret untuk endpoint cron (tanpa JWT user)."""

import hmac
import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _get_cron_secret():
    secret = os.environ.get("CLAY_CRON_SECRET", "").strip()
    if not secret:
        logger.error("CLAY_CRON_SECRET tidak diset di environment")
    return secret


def verify_cron_secret(header_value):
    """
    Bandingkan X-Cron-Secret dari header vs env var (constant-time).
    Raise HTTPException 401/500 kalau gagal.
    """
    expected = _get_cron_secret()
    if not expected:
        raise HTTPException(status_code=500, detail="Cron secret tidak dikonfigurasi")

    if not header_value:
        raise HTTPException(status_code=401, detail="Missing X-Cron-Secret header")

    if not hmac.compare_digest(str(header_value), expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")
