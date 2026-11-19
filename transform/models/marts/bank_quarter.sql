-- Conformed bank-quarter panel with the ratios ALM, early warning and the SVB case study use.
-- Amounts in thousands of USD (FDIC convention). Ratios are fractions, not percent, except the
-- FDIC-supplied *_pct columns which keep the FDIC's percent units.
with f as (
    select * from {{ ref('stg_fdic_financials') }}
)
select
    f.cert,
    f.repdte,
    f.asset, f.liab, f.eqtot, f.dep, f.depuna, f.depins,
    f.sc, f.scha, f.schf, f.scaf, f.scaa, f.lnlsgr, f.lnatres, f.chbal, f.asstlt,
    f.rbct1j, f.rwajt, f.netinc,
    f.depuna / nullif(f.dep, 0) as uninsured_deposit_share,
    f.schf - f.scha as htm_unrealized_gain_k,
    f.scaf - f.scaa as afs_unrealized_gain_k,
    (f.schf - f.scha) + (f.scaf - f.scaa) as securities_unrealized_gain_k,
    ((f.schf - f.scha) + (f.scaf - f.scaa)) / nullif(f.rbct1j, 0) as unrealized_gain_to_tier1,
    f.sc / nullif(f.asset, 0) as securities_to_assets,
    f.chbal / nullif(f.asset, 0) as cash_to_assets,
    f.asstlt / nullif(f.asset, 0) as long_term_assets_share,
    f.lnlsgr / nullif(f.dep, 0) as loans_to_deposits,
    f.nclnls / nullif(f.lnlsgr, 0) as noncurrent_loan_ratio,
    f.lnatres / nullif(f.lnlsgr, 0) as reserve_ratio,
    f.eqtot / nullif(f.asset, 0) as equity_to_assets,
    f.rbc1aaj as leverage_ratio_pct,
    f.idt1cer as cet1_ratio_pct,
    f.nimy as nim_pct,
    f.roa as roa_pct,
    b.fail_date,
    b.fail_date is not null as failed_ever
from f
left join {{ ref('bank_failure') }} b on b.cert = f.cert
