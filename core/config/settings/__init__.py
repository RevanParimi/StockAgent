# Re-export everything from base so `from core.config import settings` keeps working.
from core.config.settings.base import *  # noqa: F401, F403
from core.config.settings import base    # noqa: F401  (allows `settings.LLM_MODEL` style)
