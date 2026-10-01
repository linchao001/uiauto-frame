"""产品鉴权扩展点：框架只定义接口，具体协议由产品实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pilot.core.config import PilotConfig
    from pilot.db.client import DbClient

_UNSET_MSG = (
    "未注册 AuthProvider。请在产品仓实现 pilot.account.auth.AuthProvider，"
    "并在 conftest 中 register_auth_provider(config, ProductAuth()) "
    "（见 pilot init 生成的 account/auth.py）。"
)

# 挂在 pytest.Config 上的属性名（避免强依赖 StashKey 版本差异）
_AUTH_STASH_ATTR = "_pilot_auth_provider"


def register_auth_provider(config: Any, provider: AuthProvider) -> None:
    """在 pytest 会话注册产品 AuthProvider（通常于 ``pytest_configure``）。"""
    setattr(config, _AUTH_STASH_ATTR, provider)


def get_auth_provider(config: Any) -> AuthProvider:
    """读取已注册 Provider；未注册则返回 ``UnsetAuthProvider``。"""
    provider = getattr(config, _AUTH_STASH_ATTR, None)
    if isinstance(provider, AuthProvider):
        return provider
    return UnsetAuthProvider()


class AuthProvider(ABC):
    """产品必须实现的鉴权接口（登录 / token 存储；建号与报告版本可选）。

    框架只约定基础登录（账号密码），不含产品特有登录形态。
    """

    @abstractmethod
    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        """接口登录；返回产品自定义结构（框架不解析字段）。"""

    @abstractmethod
    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        """把登录结果转成浏览器存储项：``{storage_key: value}``（value 多为 JSON 字符串）。"""

    def recreate_test_account(
        self,
        config: PilotConfig,
        db: DbClient | None,
    ) -> None:
        """会话开始重建测试账号；默认不做事。需要时由产品覆盖。"""
        return

    def report_version_fields(self, config: PilotConfig) -> dict[str, str]:
        """写入 HTML 报告 Environment 的额外字段；默认空。"""
        return {}


class UnsetAuthProvider(AuthProvider):
    """未注册时的哨兵：调用必选方法即失败，可选方法保持默认空行为。"""

    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        raise RuntimeError(_UNSET_MSG)

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        raise RuntimeError(_UNSET_MSG)
