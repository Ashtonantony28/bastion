# 0002: US-primary regulatory lens, IFRS 9 and Basel side by side

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0

## Context
The richest public bank data is American (Freddie Mac/Fannie Mae loan level, FFIEC Call Reports,
HMDA, Fed stress scenarios, FDIC failures). Bank risk roles in the US and UK/EU expect different
frameworks.

## Decision
US frameworks are primary: CECL (ASC 326) for allowance, DFAST/CCAR for stress testing, SR 11-7 for
model risk, the US LCR/NSFR rules for liquidity. IFRS 9 staging and ECL and the Basel IRB risk
weight functions are implemented on the same portfolios alongside, with an explicit IFRS 9 vs CECL
reconciliation (M3). Basel IRRBB standardised shocks are used for interest-rate risk since the US
has no prescribed equivalent.

## Alternatives considered
EU/UK primary (IFRS 9, EBA stress test, PRA SS1/23): public EU loan-level data (ECB ED) is not
freely available, so the models would rest on US data under EU rules anyway.

## Consequences
Every formula module cites its source document. Where US and Basel differ (e.g. LCR outflow
rates), the US value is the default and the Basel value is a parameter.
