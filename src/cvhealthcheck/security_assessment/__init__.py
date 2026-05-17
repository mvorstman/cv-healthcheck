from .artifact import (
    SECURITY_ASSESSMENT_CATALOG_DIR,
    build_security_assessment_artifact,
    summarize_security_assessment_artifact,
    write_security_assessment_artifact,
)

__all__ = [
    "SECURITY_ASSESSMENT_CATALOG_DIR",
    "SECURITY_ASSESSMENT_IMPORTS_DIR",
    "SECURITY_ASSESSMENT_REGISTRY_PATH",
    "SecurityAssessmentImportError",
    "build_security_assessment_artifact",
    "import_security_assessment_csv",
    "import_security_assessment_html",
    "import_security_assessment_upload",
    "summarize_security_assessment_artifact",
    "write_security_assessment_artifact",
]


def __getattr__(name: str):
    if name == "import_security_assessment_csv":
        from .import_csv import import_security_assessment_csv

        return import_security_assessment_csv
    if name == "import_security_assessment_html":
        from .import_html import import_security_assessment_html

        return import_security_assessment_html
    if name in {
        "SECURITY_ASSESSMENT_IMPORTS_DIR",
        "SECURITY_ASSESSMENT_REGISTRY_PATH",
        "SecurityAssessmentImportError",
        "export_security_assessment_registry",
        "import_security_assessment_upload",
    }:
        from .service import (
            SECURITY_ASSESSMENT_IMPORTS_DIR,
            SECURITY_ASSESSMENT_REGISTRY_PATH,
            SecurityAssessmentImportError,
            export_security_assessment_registry,
            import_security_assessment_upload,
        )

        return {
            "SECURITY_ASSESSMENT_IMPORTS_DIR": SECURITY_ASSESSMENT_IMPORTS_DIR,
            "SECURITY_ASSESSMENT_REGISTRY_PATH": SECURITY_ASSESSMENT_REGISTRY_PATH,
            "SecurityAssessmentImportError": SecurityAssessmentImportError,
            "export_security_assessment_registry": export_security_assessment_registry,
            "import_security_assessment_upload": import_security_assessment_upload,
        }[name]
    raise AttributeError(name)
