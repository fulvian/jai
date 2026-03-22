"""Secrets Management Package.

Multi-backend secrets management with cascade lookup:
1. Doppler (if configured) - cross-platform, team sync
2. macOS Keychain (if on Mac) - local, secure
3. Environment variables - universal fallback
"""

from me4brain.secrets.manager import SecretsManager, get_secrets_manager

__all__ = [
    "SecretsManager",
    "get_secrets_manager",
]
