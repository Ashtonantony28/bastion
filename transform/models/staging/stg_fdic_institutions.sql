-- FDIC institution directory: names, state, charter class, holding company.
select
    try_cast("CERT" as bigint) as cert,
    "NAME" as name,
    "STALP" as state,
    try_cast("ACTIVE" as integer) = 1 as active,
    "BKCLASS" as charter_class,
    "NAMEHCR" as holding_company,
    try_cast("FED_RSSD" as bigint) as rssd_id
from read_csv({{ raw_path('fdic/institutions.csv') }}, header = true, all_varchar = true)
where try_cast("CERT" as bigint) is not null
