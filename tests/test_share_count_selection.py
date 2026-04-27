from __future__ import annotations

from app.services.share_count_selection import (
    point_in_time_shares_outstanding,
    shares_for_equity_value_per_share,
    shares_for_market_cap,
    shares_for_per_share_metric,
    weighted_average_basic_shares,
    weighted_average_diluted_shares,
)


def test_point_in_time_shares_outstanding_reads_value() -> None:
    assert point_in_time_shares_outstanding({"shares_outstanding": 123.0}) == 123.0


def test_weighted_average_share_helpers_read_values() -> None:
    payload = {
        "weighted_average_basic_shares": 120.0,
        "weighted_average_diluted_shares": 125.0,
    }
    assert weighted_average_basic_shares(payload) == 120.0
    assert weighted_average_diluted_shares(payload) == 125.0


def test_shares_for_market_cap_prefers_point_in_time() -> None:
    selection = shares_for_market_cap(
        {
            "shares_outstanding": 100.0,
            "weighted_average_diluted_shares": 120.0,
        }
    )

    assert selection.value == 100.0
    assert selection.source == "shares_outstanding"
    assert selection.is_proxy is False


def test_shares_for_market_cap_falls_back_to_diluted_proxy() -> None:
    selection = shares_for_market_cap(
        {
            "shares_outstanding": None,
            "weighted_average_diluted_shares": 120.0,
        }
    )

    assert selection.value == 120.0
    assert selection.source == "weighted_average_diluted_shares"
    assert selection.is_proxy is True


def test_shares_for_market_cap_reports_missing_inputs() -> None:
    selection = shares_for_market_cap({"shares_outstanding": None, "weighted_average_diluted_shares": None})

    assert selection.value is None
    assert selection.source is None
    assert selection.is_proxy is True


def test_shares_for_equity_value_per_share_prefers_point_in_time_then_diluted_proxy() -> None:
    point_in_time = shares_for_equity_value_per_share(
        {
            "shares_outstanding": 100.0,
            "weighted_average_diluted_shares": 80.0,
        }
    )
    diluted_proxy = shares_for_equity_value_per_share(
        {
            "shares_outstanding": None,
            "weighted_average_diluted_shares": 80.0,
        }
    )

    assert point_in_time.value == 100.0
    assert point_in_time.source == "shares_outstanding"
    assert point_in_time.is_proxy is False

    assert diluted_proxy.value == 80.0
    assert diluted_proxy.source == "weighted_average_diluted_shares"
    assert diluted_proxy.is_proxy is True


def test_shares_for_per_share_metric_prefers_diluted_then_basic_then_point_in_time_proxy() -> None:
    diluted = shares_for_per_share_metric(
        {
            "weighted_average_diluted_shares": 130.0,
            "weighted_average_basic_shares": 120.0,
            "shares_outstanding": 100.0,
        }
    )
    basic = shares_for_per_share_metric(
        {
            "weighted_average_diluted_shares": None,
            "weighted_average_basic_shares": 120.0,
            "shares_outstanding": 100.0,
        }
    )
    point_in_time_proxy = shares_for_per_share_metric(
        {
            "weighted_average_diluted_shares": None,
            "weighted_average_basic_shares": None,
            "shares_outstanding": 100.0,
        }
    )

    assert diluted.value == 130.0
    assert diluted.source == "weighted_average_diluted_shares"
    assert diluted.is_proxy is False

    assert basic.value == 120.0
    assert basic.source == "weighted_average_basic_shares"
    assert basic.is_proxy is False

    assert point_in_time_proxy.value == 100.0
    assert point_in_time_proxy.source == "shares_outstanding"
    assert point_in_time_proxy.is_proxy is True