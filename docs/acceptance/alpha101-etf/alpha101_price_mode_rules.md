# Alpha101 price-mode and readiness rules

The G1 Alpha101 baseline is `ALPHA101_RAW`: raw OHLC, shares, yuan, VWAP,
returns and separate amount/volume ADV.  It records `price_mode=RAW` and
`corporate_action_mode=NONE`; company-action completeness does not block it.

Raw observations resolve by fixed-release priority:

1. `final_a_stock_eod_price`;
2. `bao_a_stock_eod_info` only when the final row itself is absent;
3. governed external repair only when both are absent.

Every Bao repair retains `source_table=bao_a_stock_eod_info` and
`repair_reason=FINAL_ROW_MISSING`.  Final rows are hands/thousand-yuan and are
normalized once to shares/yuan; Bao rows are already shares/yuan.

`FINAL_ADJ` and `BAO_ADJ` are distinct modes.  A Bao `adjclose` or `adjfactor`
must never fill a missing final `adjclose`; a validated adjustment bridge is a
separate future data product.  Readiness is workflow-specific:
`raw_price_ready`, `adjusted_price_ready`, `corporate_action_ready`, and
`account_replay_ready` are independent.

Fixed-release probe: `000039.SZ`, 2020-08-19 through 2020-08-25, has no
`final_a_stock_eod_price` rows but has five Bao raw rows.  `fq='none'` resolves
those five rows from the base Bao table.  The corresponding `FINAL_ADJ` path
does not consume Bao `adjclose`; it remains a final-adjusted coverage gap.
