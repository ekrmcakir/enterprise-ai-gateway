"""Reversible PII Masking and De-anonymization (Sanitizer) Engine."""

import re
from typing import Tuple, Dict, List
from collections import OrderedDict
from app.core.telemetry import PII_ENTITIES_MASKED_TOTAL


class PIISanitizer:
    """
    Identifies sensitive Personally Identifiable Information (PII) and secrets,
    replaces them with synthetic cryptographic placeholders, and provides reversible unmasking.
    """

    # Evaluated in exact order of specificity
    PII_PATTERNS = OrderedDict([
        ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
        ("CREDIT_CARD", r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        ("TC_IDENTITY", r"\b[1-9]\d{10}\b"),  # 11-digit national ID (Turkey TC Kimlik)
        ("US_SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
        ("API_SECRET_KEY", r"\b(?:sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})\b"),
        ("PHONE_GLOBAL", r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)\d{3,4}[-.\s]?\d{4}\b"),
        ("IPV4_ADDRESS", r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
    ])

    def __init__(self):
        self.compiled_rules = [
            (entity_type, re.compile(pattern))
            for entity_type, pattern in self.PII_PATTERNS.items()
        ]

    def mask(self, text: str) -> Tuple[str, Dict[str, str], List[str]]:
        """
        Masks all recognized PII in the given text.
        Returns:
            masked_text: Text with placeholders like [PII_EMAIL_1]
            pii_mapping: Dict mapping placeholder -> original sensitive value
            entities_found: List of entity types found
        """
        if not text:
            return text, {}, []

        masked_text = text
        pii_mapping: Dict[str, str] = {}
        entities_found: List[str] = []
        counter: Dict[str, int] = {}

        for entity_type, regex in self.compiled_rules:
            matches = list(set(regex.findall(masked_text)))
            for match in matches:
                # Discard already replaced placeholder matches
                if match.startswith("[PII_") and match.endswith("]"):
                    continue

                if entity_type == "PHONE_GLOBAL":
                    digits_only = re.sub(r"\D", "", match)
                    if len(digits_only) < 10 or len(digits_only) > 13:
                        continue
                    # Skip common dates
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", match):
                        continue

                counter[entity_type] = counter.get(entity_type, 0) + 1
                token = f"[PII_{entity_type}_{counter[entity_type]}]"
                
                pii_mapping[token] = match
                masked_text = masked_text.replace(match, token)
                entities_found.append(entity_type)
                
                # Record metrics
                PII_ENTITIES_MASKED_TOTAL.labels(entity_type=entity_type).inc()

        return masked_text, pii_mapping, entities_found

    def unmask(self, text: str, pii_mapping: Dict[str, str]) -> str:
        """
        Restores masked placeholders back to their original values when returning to the user.
        """
        if not text or not pii_mapping:
            return text

        unmasked_text = text
        for token, original_val in pii_mapping.items():
            unmasked_text = unmasked_text.replace(token, original_val)

        return unmasked_text


pii_sanitizer = PIISanitizer()
