"""Proof file management helpers for the proving harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import LEAN_PROOF_DIR


@dataclass
class ProofFileController:
    """Manage proof file paths and deterministic checkpoint names."""

    workspace_root: Path = LEAN_PROOF_DIR

    def proof_path(self, job_id: str) -> Path:
        """Return the canonical proof file path for a job."""

        return self.workspace_root / f"{job_id}.lean"

    def checkpoint_path(self, job_id: str, step: int) -> Path:
        """Return the checkpoint file path for a proving step."""

        return self.workspace_root / "checkpoints" / f"{job_id}_{step:03d}.lean"
