"""Web Search Domain Package."""

from me4brain.domains.web_search.handler import WebSearchHandler


def get_handler() -> WebSearchHandler:
    return WebSearchHandler()


__all__ = ["WebSearchHandler", "get_handler"]
