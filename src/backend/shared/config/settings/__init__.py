# Re-export everything from base so from backend.shared.config import settings works.
from backend.shared.config.settings.base import *   # noqa: F401, F403
from backend.shared.config.settings import base     # noqa: F401
