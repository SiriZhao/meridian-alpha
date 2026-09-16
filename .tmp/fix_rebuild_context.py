from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
old='''                    portfolio_context=portfolio_context,
                    risk_context={"gates": list(input_blockers)},
'''
new='''                    portfolio_context={
                        "currency": account.currency,
                        "as_of": account.as_of.isoformat(),
                        "cash": str(account.cash),
                        "total_equity": str(account.total_equity),
                        "positions": [
                            {
                                "ticker": holding.ticker,
                                "market_value": str(holding.market_value),
                                "weight": str(
                                    holding.market_value / account.total_equity
                                    if account.total_equity
                                    else Decimal("0")
                                ),
                            }
                            for holding in account.holdings
                        ],
                        "account_identifier_included": False,
                    },
                    risk_context={"gates": list(input_blockers)},
'''
if old not in s: raise SystemExit("missing portfolio context call")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
