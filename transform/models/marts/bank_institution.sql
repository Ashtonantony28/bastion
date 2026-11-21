select * from {{ ref('stg_fdic_institutions') }}
qualify row_number() over (partition by cert order by active desc) = 1
