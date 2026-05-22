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


class FindingStatus(str, Enum):
    open         = "open"
    resolved     = "resolved"
    acknowledged = "acknowledged"


class ChartType(str, Enum):
    line = "line"
    bar  = "bar"
    pie  = "pie"
