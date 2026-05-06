# ── MIGRATION SHIM ────────────────────────────────────────────────────────────
# Real module: src/backend/shared/config/settings/
# Keeps `from core.config import settings` and `from core.config.settings.base import *` working.
from backend.shared.config.settings.base import *   # noqa: F401, F403
from backend.shared.config.settings import base     # noqa: F401
