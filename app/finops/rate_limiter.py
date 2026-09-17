"""Sliding-window RPM and TPM Rate Limiter."""

import time
from collections import deque
from typing import Dict, Tuple
from app.core.exceptions import RateLimitExceededException
from app.core.logging import logger


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter tracking requests and tokens per client key."""

    def __init__(self, default_rpm: int = 60, default_tpm: int = 100_000):
        self.default_rpm = default_rpm
        self.default_tpm = default_tpm
        # Key -> deque of timestamps
        self.request_timestamps: Dict[str, deque] = {}
        # Key -> deque of (timestamp, token_count)
        self.token_timestamps: Dict[str, deque] = {}

    def check_and_record(
        self, client_id: str, estimated_tokens: int = 50, rpm_limit: int = None, tpm_limit: int = None
    ):
        rpm = rpm_limit or self.default_rpm
        tpm = tpm_limit or self.default_tpm
        now = time.time()
        window_start = now - 60.0

        # Initialize deques if not present
        if client_id not in self.request_timestamps:
            self.request_timestamps[client_id] = deque()
        if client_id not in self.token_timestamps:
            self.token_timestamps[client_id] = deque()

        req_dq = self.request_timestamps[client_id]
        tok_dq = self.token_timestamps[client_id]

        # Purge items older than 60 seconds
        while req_dq and req_dq[0] < window_start:
            req_dq.popleft()
        while tok_dq and tok_dq[0][0] < window_start:
            tok_dq.popleft()

        # Check RPM
        if len(req_dq) >= rpm:
            logger.warning(f"[RATE_LIMIT] Client {client_id} exceeded RPM limit ({rpm})")
            raise RateLimitExceededException(f"RPM limit of {rpm} exceeded for this key. Try again in 60s.")

        # Check TPM
        current_tokens_in_window = sum(t[1] for t in tok_dq)
        if current_tokens_in_window + estimated_tokens > tpm:
            logger.warning(f"[RATE_LIMIT] Client {client_id} exceeded TPM limit ({tpm})")
            raise RateLimitExceededException(f"TPM limit of {tpm} exceeded for this key. Try again in 60s.")

        # Record this request
        req_dq.append(now)
        tok_dq.append((now, estimated_tokens))


rate_limiter = SlidingWindowRateLimiter()
