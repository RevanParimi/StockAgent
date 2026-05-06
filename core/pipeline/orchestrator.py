# -- MIGRATION SHIM --
# Real: src/backend/sectors/automobile/pipeline/orchestrator.py
from backend.sectors.automobile.pipeline.orchestrator import *  # noqa: F401, F403
from backend.sectors.automobile.pipeline.orchestrator import (  # noqa: F401
    AutomobileAgentOrchestrator,
    _SUB_AGENTS,
)
