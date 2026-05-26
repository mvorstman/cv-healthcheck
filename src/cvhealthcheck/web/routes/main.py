from __future__ import annotations

from .shared import bp, extract_security_assessment, is_authenticated

# Import route modules so they register handlers on the shared blueprint.
from . import basic  # noqa: F401
from . import customers  # noqa: F401
from . import development  # noqa: F401
from . import projects  # noqa: F401
from . import quick_hc  # noqa: F401
from . import quick_hc_api  # noqa: F401
from . import staging  # noqa: F401

__all__ = ["bp", "extract_security_assessment", "is_authenticated"]
