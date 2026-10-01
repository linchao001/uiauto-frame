"""pytest CLI 覆盖：browser / env 解析（不依赖 pytester 子进程）。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pilot.core.config import load_config
from pilot.core.device_filter import deselect_for_env
from pilot.pytest_plugin import _load_pilot_config, _resolve_config_path


def _write_layered(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    env_dir = config / "env"
    env_dir.mkdir(parents=True)
    (config / "product.yaml").write_text(
        "env: lab-a\nbrowser:\n  browser: chromium\n",
        encoding="utf-8",
    )
    (env_dir / "lab-a.yaml").write_text(
        "browser:\n  base_url: https://lab-a.example\n",
        encoding="utf-8",
    )
    (env_dir / "lab-b.yaml").write_text(
        "browser:\n  base_url: https://lab-b.example\n",
        encoding="utf-8",
    )
    return config


def _fake_pytestconfig(
    *,
    pilot_config: str | None = None,
    pilot_env: str | None = None,
    pilot_browser: str | None = None,
    pilot_headed: bool = False,
    rootpath: Path | None = None,
    args: tuple[str, ...] = (),
    invocation_dir: Path | None = None,
) -> SimpleNamespace:
    """模拟 pytest.Config：getoption + rootpath + args。"""
    options = {
        "--pilot-config": pilot_config,
        "pilot_env": pilot_env,
        "pilot_browser": pilot_browser,
        "--pilot-headed": pilot_headed,
    }

    def getoption(name: str, default=None):
        if name in options:
            return options[name]
        return default

    inv = None
    if invocation_dir is not None:
        inv = SimpleNamespace(dir=str(invocation_dir))
    return SimpleNamespace(
        getoption=getoption,
        rootpath=str(rootpath or Path.cwd()),
        args=list(args),
        invocation_params=inv,
    )


def test_resolve_config_path_prefers_layered_dir(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    # 同时放 legacy 文件，仍应优先分层目录
    (config / "env.yaml").write_text(
        "default:\n  browser:\n    base_url: http://legacy\n", encoding="utf-8"
    )
    cfg = _fake_pytestconfig(rootpath=tmp_path)
    assert _resolve_config_path(cfg) == config  # type: ignore[arg-type]


def test_resolve_config_path_from_cwd_when_rootpath_is_monorepo(tmp_path: Path) -> None:
    """rootpath 在仓库根、在子目录启动 pytest 时仍能发现产品 config/。"""
    monorepo = tmp_path / "repo"
    product = monorepo / "products" / "demo"
    product.mkdir(parents=True)
    config = _write_layered(product)
    (monorepo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )

    cfg = _fake_pytestconfig(
        rootpath=monorepo,
        args=("cases/test_foo.py",),
        invocation_dir=product,
    )
    # 模拟在 product 目录下启动：cwd 即 product
    prev = Path.cwd()
    try:
        import os

        os.chdir(product)
        assert _resolve_config_path(cfg) == config  # type: ignore[arg-type]
    finally:
        os.chdir(prev)


def test_load_pilot_config_browser_cli_overrides(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    pytestconfig = _fake_pytestconfig(
        pilot_config=str(config),
        pilot_browser="firefox",
    )
    cfg = _load_pilot_config(pytestconfig)  # type: ignore[arg-type]
    assert cfg.browser.browser == "firefox"
    assert cfg.browser.base_url == "https://lab-a.example"


def test_load_pilot_config_env_selects_device(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    pytestconfig = _fake_pytestconfig(
        pilot_config=str(config),
        pilot_env="lab-b",
    )
    cfg = _load_pilot_config(pytestconfig)  # type: ignore[arg-type]
    assert cfg.env == "lab-b"
    assert cfg.browser.base_url == "https://lab-b.example"


def test_device_marker_deselect_logic_matches_env() -> None:
    """与 pytest_collection_modifyitems 使用同一 deselect 逻辑。"""

    class _Marker:
        def __init__(self, *args: str) -> None:
            self.args = args
            self.kwargs: dict = {}

    class _Item:
        def __init__(self, name: str, devices: tuple[str, ...] | None) -> None:
            self.name = name
            self._devices = devices

        def get_closest_marker(self, name: str):
            if name != "device" or self._devices is None:
                return None
            return _Marker(*self._devices)

    items = [
        _Item("all", None),
        _Item("only_b", ("lab-b",)),
    ]
    kept, deselected = deselect_for_env(items, "lab-a")  # type: ignore[arg-type]
    assert [i.name for i in kept] == ["all"]
    assert [i.name for i in deselected] == ["only_b"]


def test_load_config_via_pilot_config_dir_kw(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    cfg = load_config(config_dir=config, env="lab-a")
    assert cfg.env == "lab-a"
