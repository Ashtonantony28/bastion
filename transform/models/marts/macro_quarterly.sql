-- Quarterly macro panel from FRED: average and last observation per series per quarter.
-- Satellite models (M8) regress on these; the Fed scenario variables are mapped onto them.
select
    series_id,
    last_day(make_date(year(obs_date), 3 * quarter(obs_date), 1)) as quarter_end,
    avg(value) as value_avg,
    arg_max(value, obs_date) as value_last,
    count(*) as n_obs
from {{ ref('stg_fred_observations') }}
group by all
