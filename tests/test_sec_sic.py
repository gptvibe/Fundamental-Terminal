from app.services.sec_sic import resolve_sec_sic_profile


def test_resolve_sec_sic_profile_prefers_exact_code_mapping() -> None:
    profile = resolve_sec_sic_profile("7372", "services-prepackaged software")

    assert profile.market_sector == "Technology"
    assert profile.market_industry == "Software"


def test_resolve_sec_sic_profile_falls_back_to_description_keywords() -> None:
    profile = resolve_sec_sic_profile(None, "National commercial banks")

    assert profile.market_sector == "Financials"
    assert profile.market_industry == "Banks"


def test_resolve_sec_sic_profile_falls_back_to_code_range() -> None:
    profile = resolve_sec_sic_profile("3843", None)

    assert profile.market_sector == "Healthcare"
    assert profile.market_industry == "Medical Devices"
