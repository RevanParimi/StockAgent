# Re-export everything from base so `from config import settings` keeps working.
from config.settings.base import *  # noqa: F401, F403
from config.settings import base    # noqa: F401  (allows `settings.LLM_MODEL` style)
