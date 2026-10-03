from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable


@dataclass(frozen=True)
class ReportSpec:
    key: str
    label: str
    description: str
    module: str


REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        key="explore",
        label="Explore 変動上位Page",
        description="Adobe Analytics × GSC × Screenshot × Gemini",
        module="reports.explore.report",
    ),
    ReportSpec(
        key="pd_bc",
        label="PD+BC Page",
        description="PD/BC/PIV/PIR集計 × 購入経路",
        module="reports.pd_bc.report",
    ),
)


def available_reports() -> tuple[ReportSpec, ...]:
    return REPORTS


def render_report(key: str) -> None:
    spec = next((item for item in REPORTS if item.key == key), None)
    if spec is None:
        raise KeyError(f"Unknown report type: {key}")

    module = import_module(spec.module)
    renderer: Callable[[], None] = getattr(module, "render")
    renderer()
