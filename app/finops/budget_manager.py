"""FinOps Tenant and API Key Budget Manager."""

from typing import Dict, Any
from app.config import settings
from app.core.exceptions import BudgetExceededException
from app.core.logging import logger


class BudgetManager:
    """Tracks cumulative monthly dollar spend per client/tenant and enforces caps."""

    def __init__(self, default_monthly_limit_usd: float = 50.0):
        self.default_monthly_limit_usd = default_monthly_limit_usd
        # client_id -> {"spent_usd": float, "monthly_limit_usd": float, "total_tokens": int}
        self.client_wallets: Dict[str, Dict[str, Any]] = {}

    def get_wallet(self, client_id: str) -> Dict[str, Any]:
        if client_id not in self.client_wallets:
            self.client_wallets[client_id] = {
                "spent_usd": 0.0,
                "monthly_limit_usd": self.default_monthly_limit_usd,
                "total_tokens": 0,
                "total_requests": 0,
            }
        return self.client_wallets[client_id]

    def set_budget(self, client_id: str, budget_usd: float):
        wallet = self.get_wallet(client_id)
        wallet["monthly_limit_usd"] = budget_usd

    def check_budget_preflight(self, client_id: str):
        wallet = self.get_wallet(client_id)
        if wallet["spent_usd"] >= wallet["monthly_limit_usd"]:
            logger.warning(
                f"[FINOPS] Budget exceeded for client {client_id}: "
                f"${wallet['spent_usd']:.4f} >= limit ${wallet['monthly_limit_usd']:.2f}"
            )
            raise BudgetExceededException(
                f"Monthly FinOps token budget cap (${wallet['monthly_limit_usd']:.2f}) reached.",
                current_spend=wallet["spent_usd"],
                limit=wallet["monthly_limit_usd"]
            )

    def record_usage(self, client_id: str, cost_usd: float, total_tokens: int):
        wallet = self.get_wallet(client_id)
        wallet["spent_usd"] = round(wallet["spent_usd"] + cost_usd, 6)
        wallet["total_tokens"] += total_tokens
        wallet["total_requests"] += 1


budget_manager = BudgetManager(default_monthly_limit_usd=settings.default_monthly_budget_usd)
