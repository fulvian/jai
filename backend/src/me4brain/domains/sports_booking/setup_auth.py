"""Setup script per autenticazione Playtomic.

Esegui con:
    python -m me4brain.domains.sports_booking.setup_auth

Questo script:
1. Apre il browser per login Google
2. Riceve l'id_token dal callback
3. Lo scambia con Playtomic per access/refresh tokens
4. Salva i token localmente (encrypted)
"""

import asyncio
import sys

from me4brain.domains.sports_booking.tools.playtomic_auth import interactive_login


def main():
    """Entry point per setup autenticazione."""
    success = asyncio.run(interactive_login())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
