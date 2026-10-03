from reports.registry import available_reports


def test_explore_report_is_registered():
    reports = available_reports()
    explore = next(report for report in reports if report.key == "explore")
    assert explore.module == "reports.explore.report"


def test_report_keys_are_unique():
    reports = available_reports()
    keys = [report.key for report in reports]
    assert len(keys) == len(set(keys))
