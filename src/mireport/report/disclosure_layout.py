from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING, ClassVar

from mireport.data.disclosures import getDisclosureConfig
from mireport.stringutil import stripLabelPrefix

if TYPE_CHECKING:
    from mireport.report.layout import ReportSection

L = logging.getLogger(__name__)


@dataclass(frozen=True)
class TocItem:
    idx: int
    label: str


@dataclass(frozen=True)
class TocGroup:
    heading: str | None  # None = no heading; each item renders as a flat <li>
    items: list[TocItem]


class DisclosureLayoutStrategy(ABC):
    _STRATEGY_MAP: ClassVar[dict[str, type[DisclosureLayoutStrategy]]] = {}
    _FALLBACK_STRATEGY: ClassVar[type[DisclosureLayoutStrategy] | None] = None

    def __init_subclass__(
        cls, strategy_name: str, fallback: bool = False, **kwargs: object
    ) -> None:
        super().__init_subclass__(**kwargs)
        if strategy_name in DisclosureLayoutStrategy._STRATEGY_MAP:
            raise ValueError(
                f"Strategy name {strategy_name!r} is already registered"
                f" by {DisclosureLayoutStrategy._STRATEGY_MAP[strategy_name].__name__}"
            )
        DisclosureLayoutStrategy._STRATEGY_MAP[strategy_name] = cls
        if fallback:
            if (existing := DisclosureLayoutStrategy._FALLBACK_STRATEGY) is not None:
                raise ValueError(
                    f"Fallback strategy already registered by {existing.__name__}"
                )
            DisclosureLayoutStrategy._FALLBACK_STRATEGY = cls

    @classmethod
    def _fallback(cls) -> DisclosureLayoutStrategy:
        if (fallback := cls._FALLBACK_STRATEGY) is None:
            raise ValueError("No fallback layout strategy registered")
        return fallback()

    @classmethod
    def for_entry_point(cls, entry_point: str) -> DisclosureLayoutStrategy:
        if (config := getDisclosureConfig(entry_point)) is None:
            return cls._fallback()
        layout = config["layoutStrategy"]
        ep_overrides = layout.get("entryPoints", {})
        strategy_name = ep_overrides.get(entry_point, layout.get("default"))
        if (strategy_cls := cls._STRATEGY_MAP.get(strategy_name)) is not None:
            return strategy_cls()
        L.warning(
            "Unknown layout strategy %r for entry point %r; using fallback",
            strategy_name,
            entry_point,
        )
        return cls._fallback()

    def organise_sections(self, sections: list[ReportSection]) -> list[ReportSection]:
        return sections

    @abstractmethod
    def build_toc(
        self,
        sections: list[ReportSection],
        language: str,
    ) -> list[TocGroup]: ...

    def section_label(self, section: ReportSection, language: str) -> str:
        return section.getLabel(language)

    @abstractmethod
    def page_group_key(self, section: ReportSection, language: str) -> str: ...


class SimpleLayoutStrategy(
    DisclosureLayoutStrategy, strategy_name="simple", fallback=True
):
    """Generic fallback: flat TOC, one section per page, labels unchanged."""

    def page_group_key(self, section: ReportSection, language: str) -> str:
        return section.presentation.roleUri

    def build_toc(
        self,
        sections: list[ReportSection],
        language: str,
    ) -> list[TocGroup]:
        return [
            TocGroup(
                heading=None,
                items=[TocItem(idx=idx, label=s.getLabel(language))],
            )
            for idx, s in enumerate(sections, start=1)
        ]


_VSME_SECTION_AFFINITY: dict[str, str] = {
    "B7": "B6",
    "C7": "C6",
    "C9": "C8",
}


def _old_vsme_prefix(section: ReportSection) -> str:
    return section.presentation.definition.split(".")[0]


def _short_vsme_prefix(prefix: str) -> str:
    """Shorten an old VSME group prefix, e.g. '[B07' -> 'B7'."""
    raw = prefix.removeprefix("[")
    if (suffix := raw[1:]).isdigit():
        return raw[0] + str(int(suffix))
    return raw


def _move_sections_after(
    sections: list[ReportSection], source_prefix: str, target_prefix: str
) -> list[ReportSection]:
    prefixes = {id(s): _old_vsme_prefix(s) for s in sections}
    to_move = [s for s in sections if prefixes[id(s)] == source_prefix]
    if not to_move:
        return sections
    remaining = [s for s in sections if prefixes[id(s)] != source_prefix]
    insert_pos = next(
        (i + 1 for i, s in enumerate(remaining) if prefixes[id(s)] == target_prefix),
        None,
    )
    if insert_pos is None:
        return sections
    return remaining[:insert_pos] + to_move + remaining[insert_pos:]


def _split_label(label: str) -> list[str]:
    return [p.strip() for p in label.split(" - ")]


def _item_label(parts: list[str]) -> str:
    if len(parts) >= 3:
        return " - ".join(parts[2:])
    return parts[1] if len(parts) >= 2 else parts[0]


class OldVsmeLayoutStrategy(DisclosureLayoutStrategy, strategy_name="old_vsme"):
    """Handles definitions like '[B01.000] - General information - Basis for Preparation'."""

    def organise_sections(self, sections: list[ReportSection]) -> list[ReportSection]:
        return _move_sections_after(sections, "[C02", "[B02")

    def page_group_key(self, section: ReportSection, language: str) -> str:
        short = _short_vsme_prefix(_old_vsme_prefix(section))
        return _VSME_SECTION_AFFINITY.get(short, short)

    def build_toc(
        self,
        sections: list[ReportSection],
        language: str,
    ) -> list[TocGroup]:
        groups: list[TocGroup] = []
        for prefix, group_iter in groupby(
            enumerate(sections, start=1),
            key=lambda t: _old_vsme_prefix(t[1]),
        ):
            labelled = [
                (idx, _split_label(s.getLabel(language))) for idx, s in group_iter
            ]

            # Category from the first section in the group
            first_parts = labelled[0][1]
            category = first_parts[1] if len(first_parts) >= 2 else first_parts[0]

            heading = f"[{_short_vsme_prefix(prefix)}] - {category}"
            items = [
                TocItem(idx=idx, label=_item_label(parts)) for idx, parts in labelled
            ]
            groups.append(TocGroup(heading=heading, items=items))

        return groups


class VsmeLayoutStrategy(DisclosureLayoutStrategy, strategy_name="vsme"):
    """Handles definitions like '[1010] B1 - General information - Basis for Preparation'."""

    def section_label(self, section: ReportSection, language: str) -> str:
        return stripLabelPrefix(section.getLabel(language))

    def page_group_key(self, section: ReportSection, language: str) -> str:
        prefix = _split_label(stripLabelPrefix(section.getLabel(language)))[0]
        return _VSME_SECTION_AFFINITY.get(prefix, prefix)

    def build_toc(
        self,
        sections: list[ReportSection],
        language: str,
    ) -> list[TocGroup]:
        labelled = [
            (idx, _split_label(stripLabelPrefix(s.getLabel(language))))
            for idx, s in enumerate(sections, start=1)
        ]
        groups: list[TocGroup] = []
        # Group by first part of stripped label, e.g. 'B1' from 'B1 - General information - …'
        for _, group_iter in groupby(labelled, key=lambda t: t[1][0]):
            group = list(group_iter)
            first_parts = group[0][1]
            heading = (
                " - ".join(first_parts[:2]) if len(first_parts) >= 2 else first_parts[0]
            )
            items = [TocItem(idx=idx, label=_item_label(parts)) for idx, parts in group]
            groups.append(TocGroup(heading=heading, items=items))

        return groups
