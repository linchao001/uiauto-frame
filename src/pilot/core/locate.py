"""Locator resolve / match helpers (no BrowserSettings)."""

from __future__ import annotations

from typing import Literal

from playwright.sync_api import Locator, Page

MatchMode = Literal["strict", "first", "last"] | int

_TESTID_PREFIX = "testid:"


def resolve(page: Page, target: Locator | str) -> Locator:
    if isinstance(target, str):
        if target.startswith(_TESTID_PREFIX):
            return page.get_by_test_id(target.removeprefix(_TESTID_PREFIX))
        return page.locator(target)
    return target


def apply_match(locator: Locator, match: MatchMode = "strict") -> Locator:
    if match == "strict":
        return locator
    if match == "first":
        return locator.first
    if match == "last":
        return locator.last
    if isinstance(match, int):
        if match < 0:
            raise ValueError(f"match nth must be >= 0, got {match}")
        return locator.nth(match)
    raise ValueError(f"invalid match mode: {match!r}")


def within(root: Locator, child: str) -> Locator:
    if child.startswith(_TESTID_PREFIX):
        return root.get_by_test_id(child.removeprefix(_TESTID_PREFIX))
    return root.locator(child)


def filter_has_text(locator: Locator, text: str) -> Locator:
    return locator.filter(has_text=text)


def nth(locator: Locator, index: int) -> Locator:
    return locator.nth(index)
