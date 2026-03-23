"""Official-source macro data provider package.

Providers (Phase 1):
- treasury: U.S. Treasury daily yield curve (existing, extended)
- hqm: U.S. Treasury HQM corporate bond yield curve
- bls: Bureau of Labor Statistics (CPI, Core CPI, PPI, Unemployment, Payrolls)
- bea: Bureau of Economic Analysis (GDP, PCE, Personal Income, Corporate Profits)

FRED is used as supplemental fallback only, not primary source.
"""

from __future__ import annotations
