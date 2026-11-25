-- Treasury daily par yield curve. Tenor columns change over time ("4 Mo" from Oct 2022,
-- "1.5 Month" from 2025), so read by name and parse the tenor label into months.
with raw as (
    select *
    from read_csv({{ raw_path('treasury/par_curve_*.csv') }}, header = true, all_varchar = true,
                  union_by_name = true, filename = true)
),
long as (
    unpivot raw
    on columns(* exclude ("Date", filename))
    into name tenor value raw_value
),
parsed as (
    select
        strptime("Date", '%m/%d/%Y')::date as curve_date,
        tenor,
        try_cast(regexp_extract(tenor, '^([0-9.]+)', 1) as double) as n,
        lower(regexp_extract(tenor, '([A-Za-z]+)$', 1)) as unit,
        try_cast(trim(raw_value) as double) as par_yield_pct
    from long
)
select
    curve_date,
    tenor,
    case
        when unit like 'w%' then n * 12.0 / 52.0
        when unit like 'mo%' then n
        when unit like 'y%' then n * 12.0
    end as tenor_months,
    par_yield_pct
from parsed
where par_yield_pct is not null
