from __future__ import annotations
"""Namespaces package for Me4BrAIn SDK."""

from me4brain_sdk.namespaces.working import WorkingNamespace
from me4brain_sdk.namespaces.episodic import EpisodicNamespace
from me4brain_sdk.namespaces.semantic import SemanticNamespace
from me4brain_sdk.namespaces.procedural import ProceduralNamespace
from me4brain_sdk.namespaces.cognitive import CognitiveNamespace
from me4brain_sdk.namespaces.tools import ToolsNamespace
from me4brain_sdk.namespaces.admin import AdminNamespace

__all__ = [
    "WorkingNamespace",
    "EpisodicNamespace",
    "SemanticNamespace",
    "ProceduralNamespace",
    "CognitiveNamespace",
    "ToolsNamespace",
    "AdminNamespace",
]
