from reports.registry import available_reports


def test_required_reports_are_registered():
    reports = available_reports()
    keys = {report.key for report in reports}
    assert "explore" in keys
    assert "pd_bc" in keys


def test_report_keys_are_unique():
    reports = available_reports()
    keys = [report.key for report in reports]
    assert len(keys) == len(set(keys))
