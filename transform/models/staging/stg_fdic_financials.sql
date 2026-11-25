-- FDIC BankFind financials (Call Report data). Amounts are in thousands of USD.
-- Several extracts can overlap (case study + all-banks quarters), so dedupe on (cert, repdte).
with raw as (
    select *
    from read_csv({{ raw_path('fdic/financials/*.csv') }}, header = true, union_by_name = true,
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
select *
from typed
qualify row_number() over (partition by cert, repdte order by source_file) = 1
