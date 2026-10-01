"""case_title / P0–P3 与报告 CaseMeta 解析。"""

from __future__ import annotations

from typing import Any

import pytest

from pilot.report.case_marks import (
    CaseMeta,
    format_case_summary,
    parse_case_title,
    resolve_case_meta,
    resolve_priority,
    user_properties_for_meta,
)
from pilot.report.html_utils import extras_for_text, render_case_detail_html, render_title_cell_html


class _Marker:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs


class _Callspec:
    def __init__(self, params: dict[str, Any]):
        self.params = params


class _FakeItem:
    def __init__(
        self,
        markers: dict[str, _Marker] | None = None,
        nodeid: str = "t",
        callspec: _Callspec | None = None,
    ):
        self._markers = markers or {}
        self.nodeid = nodeid
        self.callspec = callspec

    def get_closest_marker(self, name: str):
        return self._markers.get(name)


def test_parse_case_title_kwargs():
    case_id, title = parse_case_title(
        _Marker(case_id="UI-01", title="登录成功进入首页")
    )
    assert case_id == "UI-01"
    assert title == "登录成功进入首页"


def test_parse_case_title_args():
    case_id, title = parse_case_title(_Marker("UI-02", "个人中心电话校验"))
    assert case_id == "UI-02"
    assert title == "个人中心电话校验"


def test_resolve_priority_single():
    assert resolve_priority(_FakeItem({"P1": _Marker()})) == "P1"


def test_resolve_priority_includes_p3():
    assert resolve_priority(_FakeItem({"P3": _Marker()})) == "P3"


def test_resolve_priority_highest_wins(caplog: pytest.LogCaptureFixture):
    item = _FakeItem({"P0": _Marker(), "P2": _Marker()}, nodeid="demo::test_x")
    with caplog.at_level("WARNING", logger="pilot.report.case_marks"):
        assert resolve_priority(item) == "P0"
    assert "multiple priority marks" in caplog.text


def test_resolve_case_meta_combined():
    item = _FakeItem(
        {
            "case_title": _Marker(case_id="UI-01", title="登录"),
            "P0": _Marker(),
        }
    )
    meta = resolve_case_meta(item)
    assert meta == CaseMeta(case_id="UI-01", title="登录", priority="P0")
    assert meta.any is True
    assert format_case_summary(meta) == "UI-01 [P0] 登录"
    assert user_properties_for_meta(meta) == [
        ("case_id", "UI-01"),
        ("title", "登录"),
        ("priority", "P0"),
    ]


def test_resolve_case_meta_from_cases_param():
    """@cases 展开的 case 对象：用 id 填 Case ID。"""

    class _Case:
        id = "row-01"

    item = _FakeItem(callspec=_Callspec({"case": _Case()}))
    meta = resolve_case_meta(item)
    assert meta.case_id == "row-01"


def test_resolve_case_meta_from_meta_data_row():
    item = _FakeItem(
        callspec=_Callspec(
            {
                "meta_data": {
                    "id": "API-01",
                    "title": "获取用户信息",
                    "priority": "P1",
                }
            }
        )
    )
    meta = resolve_case_meta(item)
    assert meta == CaseMeta(case_id="API-01", title="获取用户信息", priority="P1")


def test_resolve_case_meta_row_overrides_marks():
    item = _FakeItem(
        {
            "case_title": _Marker(case_id="OLD", title="旧标题"),
            "P2": _Marker(),
        },
        callspec=_Callspec(
            {
                "meta_data": {
                    "id": "NEW",
                    "title": "行级标题",
                    "priority": "P0",
                }
            }
        ),
    )
    meta = resolve_case_meta(item, warn=False)
    assert meta == CaseMeta(case_id="NEW", title="行级标题", priority="P0")


def test_case_markers_registered(pytestconfig: pytest.Config):
    text = "\n".join(pytestconfig.getini("markers"))
    assert "case_title" in text


def test_render_case_detail_html_includes_title_and_steps():
    html = render_case_detail_html(
        case_id="UI-01",
        title="登录成功",
        priority="P0",
        steps=[
            ("打开登录页", "ok", ""),
            ("提交", "fail", "期望: ok\n实际: bad"),
        ],
    )
    assert "UI-01" in html
    assert "[P0]" in html
    assert "登录成功" in html
    assert "打开登录页" in html
    assert "pilot-step-reason" in html
    assert "期望: ok" in html
    assert "实际: bad" in html

    cell = render_title_cell_html(title="登录成功", detail_html=html)
    assert "pilot-title-trigger" in cell
    assert "pilot-title-popup" in cell

    plain = render_title_cell_html(title="only", detail_html="")
    assert "pilot-title-popup" not in plain
    assert plain == '<td class="col-caseTitle">only</td>'


def test_extras_for_text_optional():
    extras = extras_for_text("UI-01 [P0] 登录", name="case")
    # 未装 pytest-html 时可能为空；装了则有一条
    assert extras == [] or extras[0].get("name") == "case"
