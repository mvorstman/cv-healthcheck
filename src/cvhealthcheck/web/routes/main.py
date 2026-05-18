from __future__ import annotations

from .shared import bp, extract_security_assessment, is_authenticated

# Import route modules so they register handlers on the shared blueprint.
from . import basic  # noqa: F401
from . import development  # noqa: F401
from . import metrics  # noqa: F401
from . import quick_hc  # noqa: F401
from . import reportsplus  # noqa: F401
from . import security_assessment  # noqa: F401

__all__ = ["bp", "extract_security_assessment", "is_authenticated"]
