-- Reconcile to source: securities repricing buckets (RC-B Memo 2, debt securities only) should
-- cover total securities. Equity securities, which sat in SC before ASU 2016-01, and reporting
-- noise mean a few banks fall short, so the stated tolerance is: per report date, at most 5%
-- of banks with more than $100m of securities may have buckets outside [90%, 100.1%] of SC.
-- The Python ALM models exclude those banks (bastion.alm.balance_sheet.COVERAGE_MIN).
with b as (
    select cert, repdte, sc,
           coalesce(scnm3les,0)+coalesce(scnm3t12,0)+coalesce(scnm1t3,0)+coalesce(scnm3t5,0)
         + coalesce(scnm5t15,0)+coalesce(scnmov15,0)+coalesce(scpt3les,0)+coalesce(scpt3t12,0)
         + coalesce(scpt1t3,0)+coalesce(scpt3t5,0)+coalesce(scpt5t15,0)+coalesce(scptov15,0)
         + coalesce(sco3yles,0)+coalesce(scoov3y,0) as bucket_total
    from {{ ref('alm_position') }}
    where sc > 100000
)
select repdte, count(*) as banks,
       count(*) filter (where bucket_total < 0.90 * sc or bucket_total > 1.001 * sc) as out_of_tolerance
from b
group by repdte
having count(*) filter (where bucket_total < 0.90 * sc or bucket_total > 1.001 * sc) > 0.05 * count(*)
