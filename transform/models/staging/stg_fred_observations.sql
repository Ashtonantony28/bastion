-- FRED fredgraph CSVs: one file per series, columns (observation_date, <SERIES_ID>).
-- Unpivot to long form; gaps (empty or '.') become NULL and are dropped.
with raw as (
    select *
    from read_csv({{ raw_path('fred/*.csv') }}, header = true, all_varchar = true,
                  union_by_name = true, filename = true)
),
long as (
    unpivot raw
    on columns(* exclude (observation_date, filename))
    into name series_id value raw_value
)
select
    series_id,
    cast(observation_date as date) as obs_date,
    try_cast(nullif(trim(raw_value), '.') as double) as value
from long
where try_cast(nullif(trim(raw_value), '.') as double) is not null
