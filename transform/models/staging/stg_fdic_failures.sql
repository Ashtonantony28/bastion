-- FDIC failures and assistance transactions since 1934. Old records may lack a CERT.
select
    try_cast("CERT" as bigint) as cert,
    try_cast("FIN" as bigint) as fin,
    "NAME" as name,
    "CITYST" as city_state,
    strptime("FAILDATE", '%m/%d/%Y')::date as fail_date,
    "SAVR" as insurance_fund,
    "RESTYPE" as resolution_type,
    "RESTYPE1" as transaction_type,
    "CHCLASS1" as charter_class,
    try_cast("QBFASSET" as double) as total_assets_k,
    try_cast("QBFDEP" as double) as total_deposits_k,
    try_cast("COST" as double) as estimated_loss_k
from read_csv({{ raw_path('fdic/failures.csv') }}, header = true, all_varchar = true)
