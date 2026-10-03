from reports.pd_bc.ppt import _pct, _rate


def test_galaxy_pir_rounds_to_one_decimal():
    assert _pct(2.744230878267279, 1) == "2.7%"


def test_contact_info_previous_rate_is_available():
    previous = {"bc_visit": 5389, "contact_info": 120}
    assert _pct(_rate(previous, "contact_info"), 1) == "2.2%"
