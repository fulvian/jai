from __future__ import annotations

"""Base domain class and registry."""

from abc import ABC, abstractmethod
from typing import Any

from me4brain_sdk._http import HTTPClient


class BaseDomain(ABC):
    """Base class for domain-specific tool wrappers.

    Provides type-safe access to domain tools through dedicated methods.
    Each domain corresponds to a category in the Me4BrAIn tool registry.
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    @property
    @abstractmethod
    def domain_name(self) -> str:
        """Return the domain name (e.g., 'medical', 'finance')."""
        ...

    async def _execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool in this domain.

        Args:
            tool_name: Tool name
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        data = await self._http.post(
            "/v1/tools/execute",
            json_data={
                "tool_name": tool_name,
                "parameters": parameters,
                "context": {"domain": self.domain_name},
            },
        )
        return data


class DomainRegistry:
    """Registry providing access to all available domains.

    Lazy-loads domain instances as they're accessed.

    Example:
        domains = DomainRegistry(http_client)
        weather = await domains.geo_weather.current("London")
        drugs = await domains.medical.drug_interactions(["aspirin", "warfarin"])
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http
        self._cache: dict[str, BaseDomain] = {}

    def _get_domain(self, name: str, domain_class: type[BaseDomain]) -> BaseDomain:
        """Get or create a domain instance."""
        if name not in self._cache:
            self._cache[name] = domain_class(self._http)
        return self._cache[name]

    @property
    def medical(self) -> "MedicalDomain":
        """Medical domain - drug interactions, PubMed, clinical trials."""
        from me4brain_sdk.domains.medical import MedicalDomain

        return self._get_domain("medical", MedicalDomain)  # type: ignore

    @property
    def google_workspace(self) -> "GoogleWorkspaceDomain":
        """Google Workspace - Calendar, Gmail, Drive, Sheets."""
        from me4brain_sdk.domains.google_workspace import GoogleWorkspaceDomain

        return self._get_domain("google_workspace", GoogleWorkspaceDomain)  # type: ignore

    @property
    def finance(self) -> "FinanceDomain":
        """Finance domain - stocks, crypto, portfolio analysis."""
        from me4brain_sdk.domains.finance_crypto import FinanceDomain

        return self._get_domain("finance", FinanceDomain)  # type: ignore

    @property
    def geo_weather(self) -> "GeoWeatherDomain":
        """Geo/Weather domain - weather forecasts, geocoding."""
        from me4brain_sdk.domains.geo_weather import GeoWeatherDomain

        return self._get_domain("geo_weather", GeoWeatherDomain)  # type: ignore

    @property
    def web_search(self) -> "WebSearchDomain":
        """Web Search domain - Tavily, DuckDuckGo, Wikipedia."""
        from me4brain_sdk.domains.web_search import WebSearchDomain

        return self._get_domain("web_search", WebSearchDomain)  # type: ignore

    @property
    def entertainment(self) -> "EntertainmentDomain":
        """Entertainment - movies, music, games."""
        from me4brain_sdk.domains.entertainment import EntertainmentDomain

        return self._get_domain("entertainment", EntertainmentDomain)  # type: ignore

    @property
    def tech_coding(self) -> "TechCodingDomain":
        """Tech/Coding - GitHub, StackOverflow, code execution."""
        from me4brain_sdk.domains.tech_coding import TechCodingDomain

        return self._get_domain("tech_coding", TechCodingDomain)  # type: ignore

    @property
    def science_research(self) -> "ScienceResearchDomain":
        """Science/Research - arXiv, Semantic Scholar."""
        from me4brain_sdk.domains.science_research import ScienceResearchDomain

        return self._get_domain("science_research", ScienceResearchDomain)  # type: ignore

    @property
    def food(self) -> "FoodDomain":
        """Food - recipes, nutrition."""
        from me4brain_sdk.domains.food import FoodDomain

        return self._get_domain("food", FoodDomain)  # type: ignore

    @property
    def travel(self) -> "TravelDomain":
        """Travel - flights, airports."""
        from me4brain_sdk.domains.travel import TravelDomain

        return self._get_domain("travel", TravelDomain)  # type: ignore

    @property
    def utility(self) -> "UtilityDomain":
        """Utility - QR codes, calculators, converters."""
        from me4brain_sdk.domains.utility import UtilityDomain

        return self._get_domain("utility", UtilityDomain)  # type: ignore

    @property
    def sports_nba(self) -> "SportsNBADomain":
        """Sports/NBA - NBA analytics and stats."""
        from me4brain_sdk.domains.sports_nba import SportsNBADomain

        return self._get_domain("sports_nba", SportsNBADomain)  # type: ignore

    @property
    def knowledge_media(self) -> "KnowledgeMediaDomain":
        """Knowledge/Media - Wikipedia, News."""
        from me4brain_sdk.domains.knowledge_media import KnowledgeMediaDomain

        return self._get_domain("knowledge_media", KnowledgeMediaDomain)  # type: ignore

    @property
    def jobs(self) -> "JobsDomain":
        """Jobs - Remote job listings."""
        from me4brain_sdk.domains.jobs import JobsDomain

        return self._get_domain("jobs", JobsDomain)  # type: ignore
