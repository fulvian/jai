from __future__ import annotations
"""Medical Domain - HIPAA-aware healthcare tools."""

from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class DrugInteractionResult(BaseModel):
    """Result of drug interaction check."""

    drugs: list[str]
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    severity_summary: dict[str, int] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)


class PubMedArticle(BaseModel):
    """PubMed article result."""

    pmid: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    pub_date: str | None = None
    doi: str | None = None


class ClinicalTrial(BaseModel):
    """Clinical trial information."""

    nct_id: str
    title: str
    status: str
    phase: str | None = None
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    sponsor: str | None = None


class MedicalDomain(BaseDomain):
    """Medical domain - drug interactions, literature, clinical trials.

    All operations are designed to be HIPAA-compliant when used with
    appropriate security configurations.

    Example:
        # Check drug interactions
        result = await client.domains.medical.drug_interactions(
            drugs=["warfarin", "aspirin"],
        )

        # Search PubMed
        articles = await client.domains.medical.pubmed_search(
            query="COVID-19 treatment",
            max_results=10,
        )
    """

    @property
    def domain_name(self) -> str:
        return "medical"

    async def drug_interactions(
        self,
        drugs: list[str],
        include_severity: bool = True,
    ) -> DrugInteractionResult:
        """Check for drug-drug interactions.

        Args:
            drugs: List of drug names to check
            include_severity: Include severity analysis

        Returns:
            Interaction results with severity summary
        """
        result = await self._execute_tool(
            "drug_interactions",
            {"drugs": drugs, "include_severity": include_severity},
        )
        return DrugInteractionResult.model_validate(result.get("result", {}))

    async def drug_info(self, drug_name: str) -> dict[str, Any]:
        """Get detailed information about a drug.

        Args:
            drug_name: Drug name

        Returns:
            Drug information including indications, dosage, side effects
        """
        result = await self._execute_tool(
            "drug_info",
            {"drug_name": drug_name},
        )
        return result.get("result", {})

    async def pubmed_search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance",
    ) -> list[PubMedArticle]:
        """Search PubMed for articles.

        Args:
            query: Search query
            max_results: Maximum results
            sort: Sort order ("relevance" or "date")

        Returns:
            List of matching articles
        """
        result = await self._execute_tool(
            "pubmed_search",
            {"query": query, "max_results": max_results, "sort": sort},
        )
        articles = result.get("result", {}).get("articles", [])
        return [PubMedArticle.model_validate(a) for a in articles]

    async def clinical_trials_search(
        self,
        condition: str,
        status: str = "recruiting",
        max_results: int = 10,
    ) -> list[ClinicalTrial]:
        """Search for clinical trials.

        Args:
            condition: Medical condition
            status: Trial status ("recruiting", "active", "completed")
            max_results: Maximum results

        Returns:
            List of matching trials
        """
        result = await self._execute_tool(
            "clinical_trials_search",
            {"condition": condition, "status": status, "max_results": max_results},
        )
        trials = result.get("result", {}).get("trials", [])
        return [ClinicalTrial.model_validate(t) for t in trials]

    async def icd_lookup(
        self,
        query: str,
        version: str = "10",
    ) -> list[dict[str, Any]]:
        """Look up ICD codes.

        Args:
            query: Condition or code to search
            version: ICD version ("10" or "11")

        Returns:
            List of matching ICD codes
        """
        result = await self._execute_tool(
            "icd_lookup",
            {"query": query, "version": version},
        )
        return result.get("result", {}).get("codes", [])
