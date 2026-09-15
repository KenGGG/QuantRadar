# G1 Security Identity and Lifecycle

On 2026-09-15 the current BaoStock lifecycle observation produced 5,556
Shanghai/Shenzhen records.  Its raw receipt is
`fe96926674f45d34277d6575abbc0608e681c00b2d3974612b899a6ab0534bc8` and is
stored under the supplemental raw evidence root.  It is current-observation,
`PIT_PARTIAL` evidence, not a claim about historical availability.

The fixed base commit `uhdpedb4pr97ve80aq6nrabr66atsqtq` contains 4,916
lifecycle records.  The refreshed master combines this base with the staged
BaoStock candidate evidence, retaining identity fields and adding lifecycle
evidence at field level.

The BSE probe obtained 343 current identity records from
`akshare:stock_info_bj_name_code`; raw receipt:
`88c6627abf4dd95b94184b42c343be5387021d36c1478fe52d6869b32693260d`.
The resulting master has 5,899 records: 5,556 SH/SZ and 343 BSE. BSE records
are explicitly `identity=KNOWN`, `lifecycle=PARTIAL`, `price=UNSUPPORTED`, and
`trade_status=UNSUPPORTED`; they are not silently removed from the denominator.

The master is a metadata artifact, not a release publication. Existing release
commits remain immutable and continue to read their prior lifecycle facts.
