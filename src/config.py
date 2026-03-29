"""LeanEcon v2 configuration. Single source of truth for all runtime constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

APP_VERSION = "2.0.0-alpha"
COMING_SOON_MESSAGE = "Coming in Phase 3"

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_WORKSPACE = PROJECT_ROOT / "lean_workspace"
LEAN_PROOF_DIR = LEAN_WORKSPACE / "LeanEcon"
PREAMBLE_DIR = LEAN_PROOF_DIR / "Preamble"
EVAL_CLAIMS_DIR = PROJECT_ROOT / "evals" / "claim_sets"
CACHE_DIR = PROJECT_ROOT / ".cache"
DB_PATH = CACHE_DIR / "jobs.db"

# --- LLM Provider ---
DEFAULT_DRIVER = os.getenv("LEANECON_DRIVER", "mistral")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "labs-leanstral-2603")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# --- Lean ---
LEAN_RUN_CODE = os.getenv("LEAN_RUN_CODE", "lean_run_code")
LAKE_BUILD = os.getenv("LAKE_BUILD", "lake build")
LEAN_TIMEOUT = int(os.getenv("LEAN_TIMEOUT", "60"))

# --- Proving ---
MAX_PROVE_STEPS = int(os.getenv("MAX_PROVE_STEPS", "64"))
MAX_PROVE_TIMEOUT = int(os.getenv("MAX_PROVE_TIMEOUT", "300"))
MAX_SEARCH_TOOL_CALLS = int(os.getenv("MAX_SEARCH_TOOL_CALLS", "8"))
MAX_TOTAL_TOOL_CALLS = int(os.getenv("MAX_TOTAL_TOOL_CALLS", "40"))
PROVE_TEMPERATURE = float(os.getenv("PROVE_TEMPERATURE", "1.0"))

# --- API ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# --- Jobs ---
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "3600"))
JOB_MAX_CONCURRENT = int(os.getenv("JOB_MAX_CONCURRENT", "2"))

# --- Formalization ---
MAX_FORMALIZE_ATTEMPTS = int(os.getenv("MAX_FORMALIZE_ATTEMPTS", "3"))
FORMALIZE_TEMPERATURE = float(os.getenv("FORMALIZE_TEMPERATURE", "0.3"))

# --- Cache ---
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
