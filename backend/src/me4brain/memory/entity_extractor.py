"""Entity Extraction with SpaCy NER - OPT-014.

This module provides Named Entity Recognition (NER) using SpaCy's pre-trained models.
Falls back gracefully if SpaCy is not available.

SOTA 2026 Pattern:
    - SpaCy NER for fast, pre-trained entity recognition
    - LLM validation for domain-specific entities
    - Hybrid approach for best accuracy

Entity Types (SpaCy):
    - PERSON: People names
    - ORG: Companies, organizations
    - GPE: Countries, cities, states
    - DATE: Dates, time expressions
    - MONEY: Monetary values
    - PRODUCT: Products
    - EVENT: Events
    - WORK_OF_ART: Titles of books, songs, etc.
    - LAW: Legal documents
    - LANGUAGE: Language names

Enhanced Schema:
    (Turn)-[:MENTIONS]->(Entity {type, name, confidence})
    (Entity)-[:RELATED_TO {relation_type}]->(Entity)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc

logger = structlog.get_logger(__name__)

# Entity type mapping from SpaCy to our schema
SPACY_TO_SCHEMA_TYPES: dict[str, str] = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",
    "LOC": "location",
    "DATE": "date",
    "TIME": "time",
    "MONEY": "money",
    "PRODUCT": "product",
    "EVENT": "event",
    "WORK_OF_ART": "work_of_art",
    "LAW": "law",
    "LANGUAGE": "language",
    "FAC": "facility",
    "NORP": "demographic",
}

# Minimum confidence threshold for entity extraction
MIN_CONFIDENCE = 0.6

# Maximum entities per document (to prevent abuse)
MAX_ENTITIES_PER_DOC = 50


@dataclass
class ExtractedEntity:
    """Represents an extracted entity from text.

    Attributes:
        text: The entity text
        label: SpaCy entity type (e.g., PERSON, ORG)
        schema_type: Mapped schema type (e.g., person, organization)
        start_char: Start character position in original text
        end_char: End character position in original text
        confidence: SpaCy confidence score (0-1)
    """

    text: str
    label: str
    schema_type: str
    start_char: int
    end_char: int
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "text": self.text,
            "type": self.schema_type,
            "label": self.label,
            "start": self.start_char,
            "end": self.end_char,
            "confidence": self.confidence,
        }


@dataclass
class EntityExtractionResult:
    """Result of entity extraction from a document.

    Attributes:
        entities: List of extracted entities
        doc_text: Original document text
        spacy_available: Whether SpaCy was used
        error: Error message if extraction failed
    """

    entities: list[ExtractedEntity] = field(default_factory=list)
    doc_text: str = ""
    spacy_available: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "entities": [e.to_dict() for e in self.entities],
            "doc_text": self.doc_text[:500],  # Truncate for logging
            "spacy_available": self.spacy_available,
            "error": self.error,
        }


class EntityExtractor:
    """SpaCy-based Named Entity Recognition extractor.

    Provides fast NER using SpaCy's pre-trained models with graceful
    fallback when SpaCy is not available.

    Usage:
        extractor = EntityExtractor()
        result = extractor.extract("Apple was founded by Steve Jobs in California.")
        for entity in result.entities:
            print(f"{entity.text} -> {entity.schema_type}")
    """

    def __init__(
        self,
        model_name: str = "en_core_web_sm",
        enable_other: bool = False,
    ) -> None:
        """Initialize the entity extractor.

        Args:
            model_name: SpaCy model name to use
            enable_other: If True, include entities with 'OTHER' label
        """
        self._nlp: Language | None = None
        self._model_name = model_name
        self._enable_other = enable_other
        self._spacy_available = False
        self._init_spacy()

    def _init_spacy(self) -> None:
        """Initialize SpaCy model with lazy loading and error handling."""
        try:
            import spacy

            # Try to load the model
            try:
                self._nlp = spacy.load(self._model_name)
                self._spacy_available = True
                logger.info(
                    "spacy_model_loaded",
                    model=self._model_name,
                )
            except OSError:
                # Model not installed, try to download it
                logger.warning(
                    "spacy_model_not_found",
                    model=self._model_name,
                    message=f"Model {self._model_name} not found. Run: python -m spacy download {self._model_name}",
                )
                # Try alternative smaller model
                try:
                    self._nlp = spacy.load("en_core_web_sm")
                    self._model_name = "en_core_web_sm"
                    self._spacy_available = True
                    logger.info("spacy_fallback_model_loaded", model="en_core_web_sm")
                except OSError:
                    logger.warning(
                        "spacy_not_available",
                        message="SpaCy not available. Entity extraction will be limited.",
                    )
                    self._spacy_available = False
        except ImportError:
            logger.warning(
                "spacy_import_failed",
                message="SpaCy not installed. Install with: pip install spacy",
            )
            self._spacy_available = False

    @property
    def is_available(self) -> bool:
        """Check if SpaCy NER is available."""
        return self._spacy_available and self._nlp is not None

    def extract(self, text: str) -> EntityExtractionResult:
        """Extract entities from text using SpaCy NER.

        Args:
            text: Input text to extract entities from

        Returns:
            EntityExtractionResult with extracted entities
        """
        if not text or not text.strip():
            return EntityExtractionResult(
                entities=[],
                doc_text=text,
                spacy_available=self._spacy_available,
            )

        # Fallback: simple regex-based extraction if SpaCy not available
        if not self.is_available:
            return self._fallback_extract(text)

        try:
            return self._spacy_extract(text)
        except Exception as e:
            logger.error(
                "entity_extraction_failed",
                error=str(e),
                text_length=len(text),
            )
            return EntityExtractionResult(
                entities=[],
                doc_text=text,
                spacy_available=self._spacy_available,
                error=str(e),
            )

    def _spacy_extract(self, text: str) -> EntityExtractionResult:
        """Extract entities using SpaCy model."""
        assert self._nlp is not None

        # Process with SpaCy (use pipe for batch efficiency)
        doc: Doc = self._nlp(text[:10000])  # Limit text length

        entities: list[ExtractedEntity] = []

        for ent in doc.ents:
            # Confidence: SpaCy doesn't provide direct confidence, use default
            confidence = 0.9 if hasattr(ent, "kb_id_") and ent.kb_id_ else 0.85

            if confidence < MIN_CONFIDENCE:
                continue

            # Map SpaCy label to schema type
            schema_type = SPACY_TO_SCHEMA_TYPES.get(ent.label_, "other")

            # Skip 'OTHER' unless enabled
            if schema_type == "other" and not self._enable_other:
                continue

            # Skip entities that are too short or too long
            entity_text = ent.text.strip()
            if len(entity_text) < 2 or len(entity_text) > 200:
                continue

            # Clean entity text
            entity_text = self._clean_entity_text(entity_text)
            if not entity_text:
                continue

            entities.append(
                ExtractedEntity(
                    text=entity_text,
                    label=ent.label_,
                    schema_type=schema_type,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    confidence=confidence,
                )
            )

        # Limit entities
        entities = entities[:MAX_ENTITIES_PER_DOC]

        logger.debug(
            "entities_extracted",
            count=len(entities),
            types={e.schema_type for e in entities},
            spacy_available=True,
        )

        return EntityExtractionResult(
            entities=entities,
            doc_text=text,
            spacy_available=True,
        )

    def _fallback_extract(self, text: str) -> EntityExtractionResult:
        """Fallback extraction using regex patterns when SpaCy not available.

        This provides basic entity recognition for installations without SpaCy.
        """
        entities: list[ExtractedEntity] = []

        # Email pattern
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        for match in re.finditer(email_pattern, text):
            entities.append(
                ExtractedEntity(
                    text=match.group(),
                    label="EMAIL",
                    schema_type="email",
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence=0.95,
                )
            )

        # URL pattern
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        for match in re.finditer(url_pattern, text):
            entities.append(
                ExtractedEntity(
                    text=match.group()[:200],  # Truncate long URLs
                    label="URL",
                    schema_type="url",
                    start_char=match.start(),
                    end_char=min(match.end(), match.start() + 200),
                    confidence=0.9,
                )
            )

        # Date patterns
        date_patterns = [
            (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", "date"),
            (r"\b\d{4}-\d{2}-\d{2}\b", "date"),
            (
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b",
                "date",
            ),
            (
                r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b",
                "date",
            ),
        ]
        for pattern, schema_type in date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(
                    ExtractedEntity(
                        text=match.group(),
                        label="DATE",
                        schema_type=schema_type,
                        start_char=match.start(),
                        end_char=match.end(),
                        confidence=0.8,
                    )
                )

        # Money patterns
        money_pattern = (
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?\b|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP)\b"
        )
        for match in re.finditer(money_pattern, text, re.IGNORECASE):
            entities.append(
                ExtractedEntity(
                    text=match.group(),
                    label="MONEY",
                    schema_type="money",
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence=0.85,
                )
            )

        # Phone number pattern
        phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        for match in re.finditer(phone_pattern, text):
            entities.append(
                ExtractedEntity(
                    text=match.group(),
                    label="PHONE",
                    schema_type="phone",
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence=0.85,
                )
            )

        # Limit entities
        entities = entities[:MAX_ENTITIES_PER_DOC]

        logger.debug(
            "entities_extracted_fallback",
            count=len(entities),
            types={e.schema_type for e in entities},
            spacy_available=False,
        )

        return EntityExtractionResult(
            entities=entities,
            doc_text=text,
            spacy_available=False,
        )

    def _clean_entity_text(self, text: str) -> str:
        """Clean extracted entity text.

        Args:
            text: Raw entity text from SpaCy

        Returns:
            Cleaned text
        """
        # Remove leading/trailing whitespace
        text = text.strip()

        # Remove trailing punctuation (except for work of art titles)
        if text and len(text) > 2 and text[-1] in ".,;:!?" and text[-2].isalnum():
            # Check if removing punctuation changes the meaning
            # For names like "John.", we want "John"
            text = text[:-1].strip()

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)

        return text

    def extract_batch(self, texts: list[str]) -> list[EntityExtractionResult]:
        """Extract entities from multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of EntityExtractionResult, one per input text
        """
        if not self.is_available:
            return [self._fallback_extract(t) for t in texts]

        results: list[EntityExtractionResult] = []

        try:
            assert self._nlp is not None
            # Use pipe for batch processing (more efficient)
            for doc in self._nlp.pipe(texts, batch_size=10, disable=["tagger", "parser"]):
                entities: list[ExtractedEntity] = []

                for ent in doc.ents:
                    schema_type = SPACY_TO_SCHEMA_TYPES.get(ent.label_, "other")
                    if schema_type == "other" and not self._enable_other:
                        continue

                    entity_text = self._clean_entity_text(ent.text.strip())
                    if len(entity_text) < 2 or len(entity_text) > 200:
                        continue

                    entities.append(
                        ExtractedEntity(
                            text=entity_text,
                            label=ent.label_,
                            schema_type=schema_type,
                            start_char=ent.start_char,
                            end_char=ent.end_char,
                            confidence=0.85,
                        )
                    )

                entities = entities[:MAX_ENTITIES_PER_DOC]

                results.append(
                    EntityExtractionResult(
                        entities=entities,
                        doc_text=doc.text,
                        spacy_available=True,
                    )
                )
        except Exception as e:
            logger.error("batch_entity_extraction_failed", error=str(e))
            # Return fallback results on error
            results = [self._fallback_extract(t) for t in texts]

        return results


# Singleton instance for convenience
_entity_extractor: EntityExtractor | None = None


def get_entity_extractor() -> EntityExtractor:
    """Get the singleton entity extractor instance.

    Returns:
        EntityExtractor instance
    """
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = EntityExtractor()
    return _entity_extractor


# =============================================================================
# Integration with Session Knowledge Graph
# =============================================================================


async def extract_and_store_entities(
    session_id: str,
    tenant_id: str,
    turns: list[dict[str, Any]],
    neo4j_driver: Any,
) -> dict[str, Any]:
    """Extract entities from session turns and store in Neo4j.

    This function integrates SpaCy NER with the knowledge graph,
    creating Entity nodes and MENTIONS relationships.

    Args:
        session_id: Session ID
        tenant_id: Tenant ID
        turns: List of session turns
        neo4j_driver: Neo4j driver instance

    Returns:
        Dict with extraction stats
    """
    extractor = get_entity_extractor()

    # Combine turn content for entity extraction
    combined_text = " ".join(
        turn.get("content", "")[:500]  # Limit each turn
        for turn in turns
        if turn.get("content")
    )

    if not combined_text.strip():
        return {"entities_created": 0, "mentions_created": 0}

    # Extract entities
    result = extractor.extract(combined_text)

    if not result.entities:
        return {"entities_created": 0, "mentions_created": 0}

    entities_created = 0
    mentions_created = 0

    async with neo4j_driver.session() as session:
        for entity in result.entities:
            entity_id = f"entity_{tenant_id}_{entity.text.lower().replace(' ', '_')[:50]}"

            # Create or merge Entity node
            await session.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.name = $name,
                    e.type = $type,
                    e.tenant_id = $tenant_id,
                    e.label = $label,
                    e.confidence = $confidence,
                    e.updated_at = datetime()
                """,
                {
                    "id": entity_id,
                    "name": entity.text,
                    "type": entity.schema_type,
                    "tenant_id": tenant_id,
                    "label": entity.label,
                    "confidence": entity.confidence,
                },
            )
            entities_created += 1

            # Create MENTIONS relationship from Session to Entity
            # Find the Turn(s) that mention this entity
            for turn in turns:
                turn_content = turn.get("content", "")
                if entity.text in turn_content:
                    turn_id = turn.get("id", f"turn_{turn.get('index', 0)}")

                    await session.run(
                        """
                        MATCH (s:Session {id: $session_id})
                        MERGE (t:Turn {id: $turn_id})
                        MERGE (t)-[r:MENTIONS]->(e:Entity {id: $entity_id})
                        SET r.extracted_at = datetime()
                        """,
                        {
                            "session_id": session_id,
                            "turn_id": turn_id,
                            "entity_id": entity_id,
                        },
                    )
                    mentions_created += 1

    logger.info(
        "session_entities_extracted",
        session_id=session_id,
        entities=entities_created,
        mentions=mentions_created,
        spacy_available=result.spacy_available,
    )

    return {
        "entities_created": entities_created,
        "mentions_created": mentions_created,
        "spacy_available": result.spacy_available,
    }
