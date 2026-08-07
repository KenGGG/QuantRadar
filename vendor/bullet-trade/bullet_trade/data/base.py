"""
Deprecated legacy data.base module.

All direct jqdatasdk usage and side-effects have been removed.
Use `jq_stragety.data.auth` (delegates to current provider) or import
APIs from `jq_stragety.data.api`.
"""

from .api import get_data_provider


def auth(user: str = None, pwd: str = None, host: str = None, port: int = None):
    """Delegate authentication to the active data provider.

    Parameters mirror provider.auth(user, pwd, host, port).
    If parameters are None, providers may fall back to environment variables.
    """
    return get_data_provider().auth(user=user, pwd=pwd, host=host, port=port)


__all__ = [
    'auth',
]
