from __future__ import annotations

from pathlib import Path

from cvhealthcheck.security_assessment.registry import SecurityAssessmentArtifactRegistry

ArtifactRegistry = SecurityAssessmentArtifactRegistry


def create_artifact_registry(registry_path: Path) -> ArtifactRegistry:
    return ArtifactRegistry(registry_path)
