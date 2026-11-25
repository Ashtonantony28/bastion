-- Early-warning features (M7): CAMELS-style ratios plus rate/liquidity risk, one row per
-- bank-quarter, with the forward failure label. Year-to-date income items (NTLNLS, ELNATR) are
-- annualised by the quarter number. Growth rates require the bank to have filed exactly four
-- quarters earlier; otherwise they are NULL rather than spanning a gap.
with b as (
    select *, quarter(repdte) as qn from {{ ref('bank_quarter') }}
),
lagged as (
    select
        *,
        lag(asset, 4) over w as asset_l4,
        lag(dep, 4) over w as dep_l4,
        lag(repdte, 4) over w as repdte_l4
    from b
    window w as (partition by cert order by repdte)
)
select
    cert,
    repdte,
    ln(nullif(asset, 0)) as log_assets,
    -- Capital
    equity_to_assets,
    leverage_ratio_pct / 100.0 as tier1_leverage,
    -- Asset quality
    nclnls / nullif(lnlsgr, 0) as noncurrent_loan_ratio,
    p3asset / nullif(lnlsgr, 0) as past_due_30_89_ratio,
    reserve_ratio,
    (ntlnls * 4.0 / qn) / nullif(lnlsgr, 0) as net_chargeoff_rate,
    (elnatr * 4.0 / qn) / nullif(asset, 0) as provision_to_assets,
    -- Earnings
    roa_pct / 100.0 as roa,
    nim_pct / 100.0 as nim,
    -- Liquidity and funding
    cash_to_assets,
    securities_to_assets,
    lnlsgr / nullif(asset, 0) as loans_to_assets,
    loans_to_deposits,
    bro / nullif(dep, 0) as brokered_deposit_share,
    coredep / nullif(dep, 0) as core_deposit_share,
    voliab / nullif(liab, 0) as volatile_liability_share,
    uninsured_deposit_share,
    -- Concentration
    lnre / nullif(lnlsgr, 0) as real_estate_loan_share,
    lnci / nullif(lnlsgr, 0) as ci_loan_share,
    -- Sensitivity to market (interest-rate) risk
    long_term_assets_share,
    unrealized_gain_to_tier1,
    -- Growth
    case when repdte_l4 = repdte - interval 1 year then asset / nullif(asset_l4, 0) - 1 end as asset_growth_yoy,
    case when repdte_l4 = repdte - interval 1 year then dep / nullif(dep_l4, 0) - 1 end as deposit_growth_yoy,
    -- Label: fails within the next four quarters (strictly after the report date)
    fail_date,
    coalesce(fail_date > repdte and fail_date <= repdte + interval 1 year, false) as fail_within_4q
from lagged
