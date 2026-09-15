"""Custom exceptions and standardized error formats for Enterprise AI Gateway."""

from typing import Optional, Any, Dict
from fastapi import HTTPException, status


class GatewayException(HTTPException):
    """Base exception for Gateway errors."""

    def __init__(
        self,
        status_code: int,
        message: str,
        error_type: str = "gateway_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.error_type = error_type
        self.message = message
        self.param = param
        self.code = code
        self.details = details or {}
        
        super().__init__(
            status_code=status_code,
            detail={
                "error": {
                    "message": message,
                    "type": error_type,
                    "param": param,
                    "code": code,
                    "details": self.details,
                }
            },
        )


class AuthenticationError(GatewayException):
    """Raised when client API key is invalid or missing."""

    def __init__(self, message: str = "Incorrect or missing API key provided."):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            error_type="invalid_request_error",
            code="invalid_api_key",
        )


class SecurityFirewallBlockedException(GatewayException):
    """Raised when request violates Semantic Firewall rules (Prompt Injection, Jailbreak)."""

    def __init__(
        self,
        message: str = "Request blocked by Semantic Firewall due to high-risk prompt injection or jailbreak pattern.",
        threat_type: str = "prompt_injection",
        risk_score: float = 1.0,
        detected_patterns: Optional[list] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            error_type="firewall_security_violation",
            code="prompt_injection_detected",
            details={
                "threat_type": threat_type,
                "risk_score": risk_score,
                "detected_patterns": detected_patterns or [],
            },
        )


class RateLimitExceededException(GatewayException):
    """Raised when client exceeds RPM or TPM limit."""

    def __init__(self, message: str = "Rate limit exceeded. Please throttle your requests.", retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            message=message,
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
            details={"retry_after": retry_after},
        )


class BudgetExceededException(GatewayException):
    """Raised when client has exhausted their allocated FinOps monthly token budget."""

    def __init__(self, message: str = "Monthly token budget limit exhausted for this API key.", current_spend: float = 0.0, limit: float = 0.0):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            message=message,
            error_type="budget_exhausted_error",
            code="budget_limit_exceeded",
            details={"current_spend_usd": current_spend, "monthly_limit_usd": limit},
        )


class UpstreamProviderException(GatewayException):
    """Raised when all upstream LLM providers fail or timeout."""

    def __init__(self, message: str = "All upstream LLM providers failed or are unavailable.", status_code: int = 502):
        super().__init__(
            status_code=status_code,
            message=message,
            error_type="upstream_error",
            code="all_providers_failed",
        )
