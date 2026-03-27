"""Provider-agnostic proving harness scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from src.config import COMING_SOON_MESSAGE
from src.drivers.base import ProverDriver
from src.models import JobStatus
from src.prover.file_controller import ProofFileController
from src.prover.tool_tracker import BudgetTracker


@dataclass
class VerificationHarness:
    """Phase 2A scaffold for provider-backed proving orchestration."""

    driver: ProverDriver
    file_controller: ProofFileController
    budget_tracker: BudgetTracker

    async def verify(self, theorem_with_sorry: str, job_id: str) -> JobStatus:
        """Return a placeholder job result until Phase 3 lands."""

        _ = theorem_with_sorry
        return JobStatus(
            id=job_id,
            status="not_implemented",
            created_at="",
            updated_at="",
            result={"message": COMING_SOON_MESSAGE},
            error=None,
        )
