"""Me4BrAIn Domains Package.

Package per domain handlers modulari. Ogni sotto-package deve esporre
una funzione `get_handler()` che ritorna un'istanza di DomainHandler.

Struttura:
    domains/
    ├── __init__.py           # Questo file
    ├── sports_nba/
    │   ├── __init__.py       # get_handler() → SportsNBAHandler
    │   ├── handler.py        # DomainHandler implementation
    │   ├── tools/            # Tool implementations
    │   └── workflows/        # Chained analysis workflows
    ├── finance_crypto/
    │   └── ...
    └── google_workspace/
        └── ...

Usage:
    from me4brain.core.plugin_registry import PluginRegistry

    registry = await PluginRegistry.get_instance("tenant_id")
    # Auto-discovers all domains with get_handler()
"""
