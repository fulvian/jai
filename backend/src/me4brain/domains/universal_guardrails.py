"""Universal Guardrails Configuration for all domains and routes.

Configures adaptive guardrails for:
- All domain handlers (NBA, finance, weather, etc.)
- All API routes (memory, semantic, engine, tools, etc.)
- All response types (JSON, streaming, paginated, compressed)
- All error scenarios and edge cases
"""

from me4brain.domains.adaptive_guardrails import AdaptiveGuardrailsConfig, GuardrailsMetrics

# Global registry di configurazioni per tutti i domini e rotte
_UNIVERSAL_GUARDRAILS_REGISTRY: dict[str, AdaptiveGuardrailsConfig] = {}


def get_universal_config(domain_or_route: str) -> AdaptiveGuardrailsConfig:
    """Get or create universal guardrails config.

    Supports:
    - Domain names: "sports_nba", "finance_crypto", "geo_weather"
    - Route names: "memory", "semantic", "engine", "tools", "skills"
    - Composite: "domains/sports_nba", "memory/episodic"
    - Defaults to sensible universal config if not found
    """
    # Normalize domain/route identifier
    key = normalize_domain_key(domain_or_route)

    # Return cached config if exists
    if key in _UNIVERSAL_GUARDRAILS_REGISTRY:
        return _UNIVERSAL_GUARDRAILS_REGISTRY[key]

    # Create and cache new config
    config = create_config_for_domain(key)
    _UNIVERSAL_GUARDRAILS_REGISTRY[key] = config

    return config


def normalize_domain_key(domain: str) -> str:
    """Normalize domain/route identifier."""
    # Remove leading/trailing slashes
    domain = domain.strip("/")

    # Handle composite routes like "domains/sports_nba" or "domains/sports_nba/query"
    if "/" in domain:
        parts = domain.split("/")
        # Return the last meaningful part (skip query/execute endpoints)
        for i in range(len(parts) - 1, -1, -1):
            part = parts[i]
            if part and part not in ["query", "execute", "domains"]:
                return part
        # If all parts are skip-worthy, return first non-empty
        return parts[0] if parts else domain

    return domain


def create_config_for_domain(domain: str) -> AdaptiveGuardrailsConfig:
    """Create appropriate guardrails config based on domain/route type."""

    # Domain-specific configurations
    domain_configs = {
        # Sports domains
        "sports_nba": AdaptiveGuardrailsConfig(
            domain="sports_nba",
            max_response_bytes=150_000,  # 150KB for detailed NBA analytics
            max_items_per_page=5,  # Start with 5 games per page
            max_depth=4,
            enable_adaptive_limits=True,
            streaming_threshold_bytes=150_000,
        ),
        "sports_football": AdaptiveGuardrailsConfig(
            domain="sports_football",
            max_response_bytes=150_000,
            max_items_per_page=5,
            enable_adaptive_limits=True,
        ),
        "sports_soccer": AdaptiveGuardrailsConfig(
            domain="sports_soccer",
            max_response_bytes=150_000,
            max_items_per_page=8,
            enable_adaptive_limits=True,
        ),
        # Finance domains
        "finance_crypto": AdaptiveGuardrailsConfig(
            domain="finance_crypto",
            max_response_bytes=200_000,  # More data for crypto markets
            max_items_per_page=10,  # More crypto assets
            enable_adaptive_limits=True,
        ),
        "finance_stocks": AdaptiveGuardrailsConfig(
            domain="finance_stocks",
            max_response_bytes=200_000,
            max_items_per_page=15,
            enable_adaptive_limits=True,
        ),
        "finance_forex": AdaptiveGuardrailsConfig(
            domain="finance_forex",
            max_response_bytes=150_000,
            max_items_per_page=20,
            enable_adaptive_limits=True,
        ),
        # Travel & Geo domains
        "geo_weather": AdaptiveGuardrailsConfig(
            domain="geo_weather",
            max_response_bytes=100_000,
            max_items_per_page=20,  # Many locations
            enable_adaptive_limits=True,
        ),
        "geo_maps": AdaptiveGuardrailsConfig(
            domain="geo_maps",
            max_response_bytes=150_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        "travel_flights": AdaptiveGuardrailsConfig(
            domain="travel_flights",
            max_response_bytes=150_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        "travel_hotels": AdaptiveGuardrailsConfig(
            domain="travel_hotels",
            max_response_bytes=150_000,
            max_items_per_page=8,
            enable_adaptive_limits=True,
        ),
        # Tech & Coding domains
        "tech_coding": AdaptiveGuardrailsConfig(
            domain="tech_coding",
            max_response_bytes=100_000,
            max_items_per_page=5,
            max_depth=3,  # Code structures can be deep
            enable_adaptive_limits=True,
        ),
        "tech_devops": AdaptiveGuardrailsConfig(
            domain="tech_devops",
            max_response_bytes=150_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        # API Routes (not domains, but need guardrails too)
        "memory": AdaptiveGuardrailsConfig(
            domain="memory",
            max_response_bytes=100_000,  # Memory should be concise
            max_items_per_page=5,
            enable_adaptive_limits=True,
        ),
        "semantic": AdaptiveGuardrailsConfig(
            domain="semantic",
            max_response_bytes=200_000,  # KG can be large
            max_items_per_page=20,
            enable_adaptive_limits=True,
        ),
        "engine": AdaptiveGuardrailsConfig(
            domain="engine",
            max_response_bytes=150_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        "tools": AdaptiveGuardrailsConfig(
            domain="tools",
            max_response_bytes=100_000,
            max_items_per_page=15,
            enable_adaptive_limits=True,
        ),
        "skills": AdaptiveGuardrailsConfig(
            domain="skills",
            max_response_bytes=100_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        "working": AdaptiveGuardrailsConfig(
            domain="working",
            max_response_bytes=100_000,
            max_items_per_page=5,
            enable_adaptive_limits=True,
        ),
        "procedural": AdaptiveGuardrailsConfig(
            domain="procedural",
            max_response_bytes=100_000,
            max_items_per_page=10,
            enable_adaptive_limits=True,
        ),
        "monitoring": AdaptiveGuardrailsConfig(
            domain="monitoring",
            max_response_bytes=200_000,
            max_items_per_page=20,
            enable_adaptive_limits=True,
        ),
    }

    # Return specific config or create default
    if domain in domain_configs:
        # Create with metrics
        config = domain_configs[domain]
        if not hasattr(config, "metrics") or config.metrics is None:
            config.metrics = GuardrailsMetrics(domain=domain)
        return config

    # Default universal config for unknown domains
    return AdaptiveGuardrailsConfig(
        domain=domain,
        max_response_bytes=100_000,  # Conservative default
        max_items_per_page=5,
        enable_adaptive_limits=True,
        metrics=GuardrailsMetrics(domain=domain),
    )


def get_all_domains() -> list[str]:
    """Get list of all configured domains."""
    return list(_UNIVERSAL_GUARDRAILS_REGISTRY.keys())


def reset_universal_registry() -> None:
    """Reset the global registry (for testing)."""
    _UNIVERSAL_GUARDRAILS_REGISTRY.clear()


def configure_guardrails_for_domain(
    domain: str,
    max_response_bytes: int | None = None,
    max_items_per_page: int | None = None,
    enable_adaptive: bool = True,
) -> AdaptiveGuardrailsConfig:
    """Configure guardrails for a specific domain at runtime."""
    config = get_universal_config(domain)

    if max_response_bytes is not None:
        config.max_response_bytes = max_response_bytes
    if max_items_per_page is not None:
        config.max_items_per_page = max_items_per_page

    config.enable_adaptive_limits = enable_adaptive

    return config
