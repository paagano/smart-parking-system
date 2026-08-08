"""
Application Dependency Injection Package.

This package contains all FastAPI dependency providers used
throughout the Smart Parking System.

Dependency modules expose repositories, services and other
application components through FastAPI's dependency injection
mechanism.

Modules
-------
auth
    Authentication and authorization dependencies.

pricing
    Pricing engine dependencies.

repositories
    Repository dependency providers.

reservations
    Reservation-specific dependencies.

services
    Application service dependency providers.

wallet
    Wallet repositories and WalletService dependencies.
"""

from .auth import *

from .pricing import *

from .repositories import *

from .reservations import *

from .services import *

from .wallet import *

from .vehicles import *

__all__ = [
    #
    # Re-export everything from the dependency modules.
    #
    name
    for name in globals()
    if not name.startswith("_")
]