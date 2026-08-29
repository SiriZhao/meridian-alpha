# Host account integration runbook

1. Host obtains authorized current account facts outside Meridian.
2. Host removes identifiers, credentials, and raw connector material.
3. Host creates a `HostAccountSnapshotEnvelope` and calls the read-only
   validation tool.
4. Host calls the read-only daily-analysis tool.
5. Host renders: 今日状态, 账户概览, 市场环境, 今日重点股票, Quant 信号,
   AI/TradingAgents 研判, 证据与风险, 目标组合, 操作清单, 当前阻塞项.

Human labels are distinct: 建议 (recommendation), 草稿 (draft), 可手动录入
(manual-entry candidate), 已执行 (executed). The final label requires a newer
account snapshot; Meridian does not emit it itself.