"""鉴权扩展点：产品实现 AuthProvider。"""

from pilot.account.auth import (
    AuthProvider,
    UnsetAuthProvider,
    get_auth_provider,
    register_auth_provider,
)

__all__ = [
    "AuthProvider",
    "UnsetAuthProvider",
    "get_auth_provider",
    "register_auth_provider",
]
