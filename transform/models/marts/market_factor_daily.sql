-- Daily market-risk factor levels and returns used by bastion.market (M4).
--   equity_<industry>   simple daily total return (French 12 industries, value weighted)
--   equity_market       Mkt-RF + RF (simple daily total return)
--   rf_daily            daily risk-free return
--   fx_<pair>           FRED noon buying rate level (USD per unit of foreign, JPY/CAD inverted)
--   vix                 CBOE VIX close (level, vol points)
--   baa_spread          Moody's Baa minus 10y Treasury (percent level)
-- Kind = 'return' or 'level' so consumers know whether to difference.
with fr as (
    select obs_date, dataset, series, ret from {{ ref('stg_french_daily') }}
),
eq as (
    select obs_date, 'equity_' || lower(series) as factor, ret as value, 'return' as kind
    from fr where dataset = 'industry12_vw'
    union all
    select obs_date, 'equity_market', sum(ret) filter (where series in ('Mkt-RF', 'RF')), 'return'
    from fr where dataset = 'factors' group by obs_date
    union all
    select obs_date, 'rf_daily', max(ret) filter (where series = 'RF'), 'return'
    from fr where dataset = 'factors' group by obs_date
),
fred as (
    select obs_date,
           case series_id
               when 'DEXUSEU' then 'fx_eur' when 'DEXUSUK' then 'fx_gbp'
               when 'DEXJPUS' then 'fx_jpy' when 'DEXCAUS' then 'fx_cad'
               when 'VIXCLS' then 'vix' when 'BAA10Y' then 'baa_spread'
           end as factor,
           case when series_id in ('DEXJPUS', 'DEXCAUS') then 1.0 / value else value end as value,
           'level' as kind
    from {{ ref('stg_fred_observations') }}
    where series_id in ('DEXUSEU', 'DEXUSUK', 'DEXJPUS', 'DEXCAUS', 'VIXCLS', 'BAA10Y')
)
select * from eq where value is not null
union all
select * from fred
