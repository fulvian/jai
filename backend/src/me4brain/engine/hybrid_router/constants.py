"""Constants for Hybrid Router and Collection Management.

Defines unified collection names and metadata schema for agent capabilities.
"""

# =============================================================================
# Unified Collection Architecture (SINGLE SOURCE OF TRUTH)
# =============================================================================

# Main unified collection for all capabilities (tools + skills)
# This is the ONLY collection that should be used for retrieval
CAPABILITIES_COLLECTION = "me4brain_capabilities"

# Legacy aliases - DO NOT USE, kept for reference only
TOOL_CATALOG_COLLECTION_DEPRECATED = "tool_catalog"
TOOLS_AND_SKILLS_COLLECTION_DEPRECATED = "tools_and_skills"
ME4BRAIN_SKILLS_COLLECTION_DEPRECATED = "me4brain_skills"
TOOLS_COLLECTION_DEPRECATED = "tools"

# Embedding dimensions
EMBEDDING_DIM = 1024  # BGE-M3

# =============================================================================
# Capability Types for Metadata Filtering
# =============================================================================

CAPABILITY_TYPE_TOOL = "tool"  # Static hardcoded domain tools
CAPABILITY_TYPE_SKILL = "skill"  # Auto-generated skills
CAPABILITY_TYPE_MUSCLE = "muscle_memory"  # Cached execution patterns

# Subtypes for finer granularity
CAPABILITY_SUBTYPE_STATIC = "static"  # From domain handlers (tools)
CAPABILITY_SUBTYPE_CRYSTALLIZED = "crystallized"  # Voyager-style verified skills
CAPABILITY_SUBTYPE_LEARNED = "learned"  # From user interactions

# =============================================================================
# Priority Boost (for score reranking)
# =============================================================================

# Static tools get higher priority (proven reliability)
PRIORITY_BOOST_STATIC_TOOL = 1.3

# Crystallized skills (proven success patterns)
PRIORITY_BOOST_CRYSTALLIZED_SKILL = 1.1

# New/learned skills (needs validation)
PRIORITY_BOOST_LEARNED_SKILL = 0.9

# Muscle memory patterns
PRIORITY_BOOST_MUSCLE_MEMORY = 1.0

# =============================================================================
# Retrieval Configuration
# =============================================================================

# Minimum similarity score for inclusion
MIN_SIMILARITY_SCORE = 0.48

# Default top-k for coarse retrieval
DEFAULT_COARSE_TOP_K = 30

# Max payload size limit (bytes)
MAX_PAYLOAD_BYTES = 100_000
