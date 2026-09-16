"""Prompt Injection and Jailbreak Detection Engine."""

import re
from typing import List, Tuple, Dict, Any
from app.core.logging import logger


class PromptInjectionDetector:
    """Detects prompt injections, jailbreaks, role overrides, and system leakage probes."""

    # High-risk prompt injection and jailbreak signatures
    SIGNATURE_PATTERNS = [
        # Instruction Overrides
        (r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules|commands)", 0.95, "instruction_override"),
        (r"(?i)\bdisregard\s+(all\s+)?(previous|prior|above|system)\s+(instructions|directives|rules)", 0.95, "instruction_override"),
        (r"(?i)\bforget\s+(everything|all\s+prior\s+instructions|your\s+system\s+prompt)", 0.90, "instruction_override"),
        (r"(?i)\byou\s+are\s+now\s+in\s+(developer|unrestricted|god|dan|jailbreak)\s+mode", 0.98, "jailbreak_dan_mode"),
        (r"(?i)\bdo\s+anything\s+now\b", 0.95, "jailbreak_dan_mode"),
        (r"(?i)\bpretend\s+you\s+have\s+no\s+(safety|ethical|content)\s+guidelines", 0.95, "jailbreak_persona"),
        
        # System Prompt Leakage
        (r"(?i)\b(print|reveal|output|display|show|dump)\s+(?:your\s+|the\s+|all\s+|initial\s+|system\s+|hidden\s+)*(?:prompt|instructions|rules)", 0.92, "system_leak_probe"),
        (r"(?i)\bwhat\s+(?:is|are)\s+the\s+(?:exact\s+words\s+of\s+your|rules\s+given\s+in\s+your|system\s+instructions|hidden\s+prompt)", 0.88, "system_leak_probe"),
        
        # Delimiter Hacking & XML/Markdown boundary injection
        (r"(?i)<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", 0.99, "token_delimiter_attack"),
        (r"(?i)\[SYSTEM_PROMPT\]|\[SYSTEM\]|```system", 0.90, "system_boundary_spoofing"),
        (r"(?i)\bbase64\s*:\s*[a-zA-Z0-9+/=]{20,}", 0.75, "obfuscation_base64"),
        
        # Malicious Roleplay / Jailbreak Framing
        (r"(?i)\bfrom\s+now\s+on,\s+you\s+will\s+act\s+as\s+[a-zA-Z0-9_-]+\s+who\s+can\s+bypass\s+all\s+filters", 0.95, "roleplay_bypass"),
        (r"(?i)\bhypothetical\s+scenario\s+where\s+morality\s+and\s+laws\s+do\s+not\s+apply", 0.85, "hypothetical_evasion"),
    ]

    def __init__(self, sensitivity_threshold: float = 0.70):
        self.sensitivity_threshold = sensitivity_threshold
        self.compiled_patterns = [
            (re.compile(pattern), weight, tag)
            for pattern, weight, tag in self.SIGNATURE_PATTERNS
        ]

    def scan_text(self, text: str) -> Tuple[bool, float, List[Dict[str, Any]]]:
        """
        Scans input text for prompt injection / jailbreak indicators.
        Returns: (is_threat_detected, max_risk_score, list_of_matched_patterns)
        """
        if not text:
            return False, 0.0, []

        matches = []
        max_score = 0.0

        for regex, weight, tag in self.compiled_patterns:
            found = regex.findall(text)
            if found:
                max_score = max(max_score, weight)
                matches.append({
                    "tag": tag,
                    "weight": weight,
                    "sample": str(found[0])[:60]
                })

        # Length anomaly / repetition heuristic check
        if len(text) > 10000:
            words = text.split()
            if len(set(words)) < (len(words) * 0.15):
                max_score = max(max_score, 0.75)
                matches.append({"tag": "token_repetition_overflow", "weight": 0.75, "sample": "repeated_patterns"})

        is_threat = max_score >= self.sensitivity_threshold
        if is_threat:
            logger.warning(f"[FIREWALL] Prompt Injection Detected: score={max_score}, threats={matches}")

        return is_threat, max_score, matches


injection_detector = PromptInjectionDetector()
