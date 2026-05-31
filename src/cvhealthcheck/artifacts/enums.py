from enum import Enum


class SourceType(str, Enum):
    reportsplus_rest = "reportsplus_rest"
    rest             = "rest"
    rest_commserve   = "rest_commserve"
    csv_import       = "csv_import"
    html_import      = "html_import"
    json_import      = "json_import"


class ArtifactStatus(str, Enum):
    good     = "good"
    warning  = "warning"
    critical = "critical"
    unknown  = "unknown"


class FindingSeverity(str, Enum):
    critical = "critical"
    warning  = "warning"
    good     = "good"
    info     = "info"
    # ADR 0004 evaluative face: explicit suppression severity. Used by
    # mute_on_sentinel (a metric whose value is "n/a" is not judged) and, in
    # phase 8, by override rules that neutralize a prior layer's verdict.
    muted    = "muted"


class FindingStatus(str, Enum):
    open         = "open"
    resolved     = "resolved"
    acknowledged = "acknowledged"


class ChartType(str, Enum):
    line = "line"
    bar  = "bar"
    pie  = "pie"
