-- One row per bank-quarter of ALM inputs; NULL buckets mean "not reported" and become 0 in
-- the Python models only where the Call Report instructions imply zero.
select * exclude (source_file) from {{ ref('stg_fdic_alm') }}
