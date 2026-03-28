"""Official-source macro data provider package.

Providers:
- treasury: U.S. Treasury daily yield curve (existing, extended)
- hqm: U.S. Treasury HQM corporate bond yield curve
- bls: Bureau of Labor Statistics (CPI, PPI, ECI, labor, JOLTS)
- bea: Bureau of Economic Analysis (PCE, GDP by industry)
- census: Census economic indicators (M3, retail sales)

FRED remains supplemental only for legacy macro context fields.
"""

from __future__ import annotations
