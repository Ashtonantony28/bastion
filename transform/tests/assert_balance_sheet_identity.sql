-- Reconcile to source (CLAUDE.md rule 4): total assets = total liabilities + total equity
-- capital, within 0.1% (rounding in reported thousands).
select cert, repdte, asset, liab, eqtot
from {{ ref('bank_quarter') }}
where abs(asset - (liab + eqtot)) > greatest(1.0, 0.001 * asset)
