class AdapterNotFoundError(Exception):
    """Raised when no adapter is registered for the given subject_id + source_type combination."""
