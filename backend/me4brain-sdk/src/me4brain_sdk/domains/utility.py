"""Utility Domain - QR codes, calculators, converters."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel

from me4brain_sdk.domains._base import BaseDomain


class CalculationResult(BaseModel):
    """Math calculation result."""

    expression: str
    result: float | str
    formatted: str | None = None


class QRCodeResult(BaseModel):
    """QR code generation result."""

    data: str
    image_url: str | None = None
    format: str = "png"


class UtilityDomain(BaseDomain):
    """Utility domain - QR codes, calculators, converters.

    Example:
        # Calculate expression
        result = await client.domains.utility.calculate("sqrt(144) + 2^3")

        # Generate QR code
        qr = await client.domains.utility.qr_code("https://example.com")
    """

    @property
    def domain_name(self) -> str:
        return "utility"

    async def calculate(self, expression: str) -> CalculationResult:
        """Evaluate a mathematical expression.

        Args:
            expression: Math expression to evaluate

        Returns:
            Calculation result
        """
        result = await self._execute_tool("calculator", {"expression": expression})
        return CalculationResult.model_validate(result.get("result", {}))

    async def qr_code(
        self,
        data: str,
        size: int = 200,
    ) -> QRCodeResult:
        """Generate a QR code.

        Args:
            data: Data to encode
            size: Image size in pixels

        Returns:
            QR code result with image URL
        """
        result = await self._execute_tool(
            "qr_generate",
            {"data": data, "size": size},
        )
        return QRCodeResult.model_validate(result.get("result", {}))

    async def unit_convert(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> dict[str, Any]:
        """Convert between units.

        Args:
            value: Value to convert
            from_unit: Source unit
            to_unit: Target unit

        Returns:
            Conversion result
        """
        result = await self._execute_tool(
            "unit_convert",
            {"value": value, "from_unit": from_unit, "to_unit": to_unit},
        )
        return result.get("result", {})

    async def uuid_generate(self, version: int = 4) -> str:
        """Generate a UUID.

        Args:
            version: UUID version (1, 4, or 5)

        Returns:
            Generated UUID string
        """
        result = await self._execute_tool("uuid_generate", {"version": version})
        return result.get("result", {}).get("uuid", "")

    async def hash_text(
        self,
        text: str,
        algorithm: str = "sha256",
    ) -> str:
        """Hash text.

        Args:
            text: Text to hash
            algorithm: Hash algorithm (md5, sha1, sha256, sha512)

        Returns:
            Hash string
        """
        result = await self._execute_tool(
            "hash_text",
            {"text": text, "algorithm": algorithm},
        )
        return result.get("result", {}).get("hash", "")
