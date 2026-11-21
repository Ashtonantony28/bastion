-- FDIC ALM extract (repricing/maturity buckets, deposit mix, HQLA proxies). Thousands of USD.
with raw as (
    select *
    from read_csv({{ raw_path('fdic/alm/*.csv') }}, header = true, union_by_name = true,
                  filename = true, normalize_names = true,
                  types = {'cert': 'BIGINT', 'repdte': 'VARCHAR'})
),
typed as (
    select
        cast(cert as bigint) as cert,
        strptime(repdte, '%Y%m%d')::date as repdte,
        columns(* exclude (cert, repdte, filename))::double,
        filename as source_file
    from raw
)
select * from typed
qualify row_number() over (partition by cert, repdte order by source_file) = 1
