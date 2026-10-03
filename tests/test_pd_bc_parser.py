from reports.pd_bc.parser import FUNNEL_ROWS


def test_other_segment_uses_corrected_name():
    assert FUNNEL_ROWS["B Other [2~6]"] == "Other"


def test_old_other_segment_name_remains_backward_compatible():
    assert FUNNEL_ROWS["B Order [2~6]"] == "Other"
