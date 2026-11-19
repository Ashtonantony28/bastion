-- Fed supervisory scenario tables (domestic), one file per vintage year and scenario.
-- Files live at fed_scenarios/<year>/<scenario>_domestic.csv (see ingest/fed_scenarios.py).
with raw as (
    select *
    from read_csv({{ raw_path('fed_scenarios/*/*_domestic.csv') }}, header = true,
                  all_varchar = true, union_by_name = true, filename = true)
),
long as (
    unpivot raw
    on columns(* exclude ("Scenario Name", "Date", filename))
    into name variable value raw_value
)
select
    cast(regexp_extract(filename, 'fed_scenarios/(\d{4})/', 1) as integer) as vintage_year,
    regexp_extract(filename, '/([a-z_]+)_domestic\.csv$', 1) as scenario,
    "Scenario Name" as scenario_name,
    cast(split_part("Date", ' Q', 1) as integer) as year,
    cast(split_part("Date", ' Q', 2) as integer) as quarter,
    last_day(make_date(cast(split_part("Date", ' Q', 1) as integer),
                       3 * cast(split_part("Date", ' Q', 2) as integer), 1)) as quarter_end,
    variable,
    try_cast(trim(raw_value) as double) as value
from long
where try_cast(trim(raw_value) as double) is not null
