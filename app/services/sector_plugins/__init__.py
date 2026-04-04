from app.services.sector_plugins.bts_airlines import PLUGIN as BTS_AIRLINES_PLUGIN
from app.services.sector_plugins.cftc_cot import PLUGIN as CFTC_COT_PLUGIN
from app.services.sector_plugins.eia_power import PLUGIN as EIA_POWER_PLUGIN
from app.services.sector_plugins.fed_h8_banking import PLUGIN as FED_H8_BANKING_PLUGIN
from app.services.sector_plugins.fhfa_housing import PLUGIN as FHFA_HOUSING_PLUGIN
from app.services.sector_plugins.usda_wasde import PLUGIN as USDA_WASDE_PLUGIN

SECTOR_PLUGINS = (
    FED_H8_BANKING_PLUGIN,
    EIA_POWER_PLUGIN,
    FHFA_HOUSING_PLUGIN,
    BTS_AIRLINES_PLUGIN,
    CFTC_COT_PLUGIN,
    USDA_WASDE_PLUGIN,
)

__all__ = ["SECTOR_PLUGINS"]