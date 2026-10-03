from reports.pd_bc.parser import FUNNEL_SEGMENTS


def test_other_segment_uses_corrected_name():
    assert FUNNEL_SEGMENTS["B Other [2~6]"] == "other"


def test_old_other_segment_name_remains_backward_compatible():
    assert FUNNEL_SEGMENTS["B Order [2~6]"] == "other"
