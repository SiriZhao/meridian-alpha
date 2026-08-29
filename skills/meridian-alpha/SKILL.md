---
name: meridian-alpha
description: Safely orchestrate a current brokerage AccountSnapshot through Meridian Alpha without executing brokerage orders.
---

# Meridian Alpha

When a user says “运行 Meridian Alpha”, “跑今天的策略”, “分析今天账户”, or
“给我今天限价单”, use this workflow.

1. Use only a currently authorized financial-data capability to locate the
   user’s Charles Schwab brokerage and check its connection state.
2. If supported and freshness is visibly insufficient, request a refresh/resync.
3. Obtain current cash, holdings, latest balance, and relevant recent investment
   transactions. Do not read or expose the full account number.
4. Convert the data to a sanitized `AccountSnapshot` and call
   `validate_account_snapshot`.
5. Call `run_daily_analysis` with that snapshot. Its description is: **Use this
   after obtaining the user’s current brokerage account snapshot from an
   authorized connected financial-data source.**
6. If the status is blocked, `NO_CAPITAL`, or `DRAFT`, state why and do not
   present an executable ticket.
7. Only for `READY_FOR_MANUAL_ENTRY`, retrieve and display the Manual Order
   Ticket. The user manually enters each order at Schwab.
8. Never execute a brokerage order, never infer a fill, and obtain a new account
   snapshot the next trading day.

Yesterday’s recommendation is never portfolio truth. Current brokerage
holdings are portfolio truth.

If an authorized current account source is unavailable, do not guess. Report
`ACCOUNT_DATA_UNAVAILABLE` and do not call the decision workflow with invented
data.

Read [workflow.md](references/workflow.md), [account-contract.md](references/account-contract.md),
[safety.md](references/safety.md), and [order-ticket.md](references/order-ticket.md).
