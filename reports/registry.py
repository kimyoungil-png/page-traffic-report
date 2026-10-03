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


# Adding a report should only require:
# 1) a new reports/<report_name>/report.py with render()
# 2) one entry here.
#
# Existing report modules do not import one another.
REPORTS: tuple[ReportSpec, ...] = (
    ReportSpec(
        key="explore",
        label="Explore 変動上位Page",
        description="Adobe Analytics × GSC × Screenshot × Gemini",
        module="reports.explore.report",
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
