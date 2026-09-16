"""Output Guardrails and Secret Leakage Prevention."""

import re
from typing import Tuple, List
from app.core.logging import logger


class OutputGuardrail:
    """Verifies LLM responses for unwanted secret leaks or extreme toxicity before sending to client."""

    LEAK_PATTERNS = [
        (r"(?i)aws_secret_access_key\s*=\s*['\"][a-zA-Z0-9/+=]{40}['\"]", "aws_secret_key"),
        (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{50,}", "jwt_auth_token"),
        (r"(?i)-----BEGIN\s+PRIVATE\s+KEY-----", "rsa_private_key"),
        (r"(?i)postgres(?:ql)?://[a-zA-Z0-9_]+:[a-zA-Z0-9_@]+@[a-zA-Z0-9_\.\-]+:\d+/[a-zA-Z0-9_]+", "db_connection_uri"),
    ]

    def __init__(self):
        self.compiled_leaks = [
            (re.compile(pattern), tag) for pattern, tag in self.LEAK_PATTERNS
        ]

    def inspect_output(self, text: str) -> Tuple[bool, str, List[str]]:
        """
        Inspects model response. If secrets are detected, redacts them.
        Returns: (is_clean, sanitized_response, detected_violations)
        """
        if not text:
            return True, text, []

        sanitized = text
        violations = []

        for regex, tag in self.compiled_leaks:
            if regex.search(sanitized):
                violations.append(tag)
                sanitized = regex.sub("[REDACTED_SECRET_LEAK_PREVENTED]", sanitized)
                logger.error(f"[OUTPUT_GUARD] Secret leak prevented in LLM response: type={tag}")

        is_clean = len(violations) == 0
        return is_clean, sanitized, violations


output_guard = OutputGuardrail()
