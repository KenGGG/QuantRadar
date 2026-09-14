# DataHub V3 P0 — G1 First Snapshot Release

The first published V3 snapshot release is `Re2733b3b65f15f68`, with base
commit `uhdpedb4pr97ve80aq6nrabr66atsqtq` and supplemental commit
`hjfqs078gs84movadfda1jjoqje936vk`.

Release-pinned reads verified the following current observations:

| Snapshot | Members | source_date | PIT status |
| --- | ---: | --- | --- |
| CSI300 constituents | 300 | 2026-09-14 | PARTIAL |
| CSI500 constituents | 500 | 2026-09-14 | PARTIAL |
| CSI1000 constituents | 1000 | 2026-09-14 | PARTIAL |
| SW `801010` components | 104 | NULL | PARTIAL |

The SW source's member inclusion date is retained at member level. Its snapshot
has no source market date and is therefore excluded from `as_of` queries. The
CSI source date is retained only as a source-declared date; none of these rows
claim historical effective-date or strict-PIT eligibility.

The remaining G1 work is the formal collection CLI and the 20:30
`Asia/Shanghai` scheduler, gated by QuantRadar's fixed SSE calendar.
