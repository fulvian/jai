"""Knowledge & Media Domain Package."""

from me4brain.domains.knowledge_media.handler import KnowledgeMediaHandler


def get_handler() -> KnowledgeMediaHandler:
    return KnowledgeMediaHandler()


__all__ = ["KnowledgeMediaHandler", "get_handler"]
