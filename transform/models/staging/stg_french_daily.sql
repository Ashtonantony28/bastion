-- Kenneth French daily returns (percent), normalised by ingest/french.py. Missing = -99.99/-999.
with raw as (
    select *
    from read_csv({{ raw_path('french/*_daily.csv') }}, header = true, all_varchar = true,
                  union_by_name = true, filename = true)
),
long as (
    unpivot raw on columns(* exclude (date, filename)) into name series value raw_value
)
select
    strptime(date, '%Y%m%d')::date as obs_date,
    regexp_extract(filename, '/([a-z0-9_]+)_daily\.csv$', 1) as dataset,
    series,
    try_cast(raw_value as double) / 100.0 as ret
from long
where try_cast(raw_value as double) is not null
  and try_cast(raw_value as double) > -99
