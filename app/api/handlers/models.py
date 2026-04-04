from __future__ import annotations

from app.api.handlers._dispatch import route_handler


company_models = route_handler("company_models")
company_oil_scenario = route_handler("company_oil_scenario")
company_oil_scenario_overlay = route_handler("company_oil_scenario_overlay")
latest_model_evaluation = route_handler("latest_model_evaluation")


__all__ = ["company_models", "company_oil_scenario", "company_oil_scenario_overlay", "latest_model_evaluation"]