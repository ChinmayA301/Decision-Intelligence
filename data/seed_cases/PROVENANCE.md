# Seed case provenance

## Batch 1 — original curated set (30 cases)

Hand-curated corporate decisions. `review_status: reviewed`, `reviewed_by: seed_curator_v1`.
One case (`netflix-qwikster-2011`) is `draft` and is therefore excluded from the retrieval
store unless the loader is run with `--force-status reviewed`.

## Batch 2 — Billion Dollar PDFs derived set (23 cases, 2026-08)

Drafted from decisions documented in the [Billion Dollar PDFs](https://billiondollarpdf.com)
directory — an open index of memos, papers and decks that moved capital. Each case links to
its directory entry plus a second independent source (book, regulatory filing, or the primary
document).

**These are `review_status: draft` and are AI-drafted from public record, not human-verified.**
They are excluded from the retrieval store unless built with `--force-status reviewed`.
Spot-check the outcome labels and factual claims before presenting any of them as curated.

Cases added:

| Case | Domain | Outcome |
|---|---|---|
| chanos-enron-short-2000 | capital_allocation | success |
| burry-scion-subprime-2005 | capital_allocation | success |
| einhorn-lehman-short-2008 | capital_allocation | success |
| einhorn-allied-capital-2002 | capital_allocation | mixed |
| ackman-herbalife-short-2012 | capital_allocation | failure |
| muddy-waters-sino-forest-2011 | capital_allocation | success |
| citron-valeant-2015 | capital_allocation | success |
| hindenburg-nikola-2020 | capital_allocation | success |
| muddy-waters-luckin-2020 | capital_allocation | success |
| hindenburg-adani-2023 | capital_allocation | mixed |
| ard-dec-investment-1957 | capital_allocation | success |
| sequoia-youtube-investment-2005 | capital_allocation | success |
| sequoia-airbnb-series-a-2009 | capital_allocation | success |
| chamath-spac-ipo2-2020 | capital_allocation | failure |
| buffett-buy-american-2008 | capital_allocation | success |
| grantham-reinvesting-terrified-2009 | capital_allocation | success |
| grantham-last-dance-2021 | capital_allocation | mixed |
| sequoia-rip-good-times-2008 | capital_allocation | success |
| sequoia-adapting-to-endure-2022 | capital_allocation | mixed |
| microsoft-internet-tidal-wave-1995 | market_entry | success |
| tesla-master-plan-2006 | market_entry | success |
| fairchild-semiconductor-founding-1957 | market_entry | success |
| deepseek-r1-open-weights-2025 | market_entry | success |

## Known bias in this batch — read before trusting base rates

**Survivorship bias.** The source directory indexes documents *because they moved capital* —
i.e. because they turned out to matter. Drawing cases from it therefore selects for decisions
that worked. This batch is 74% success (17/23), which pushed the whole library from 60% to
66% success. A base rate computed over these cases overstates how often comparable decisions
succeed in the wild, and should not be quoted as an empirical success rate for a decision class.

**Domain concentration.** These documents are overwhelmingly investment and strategy artifacts,
so 19 of 23 land in `capital_allocation`, taking that domain from 5 cases to 24 — nearly half
the library. Because retrieval filters by domain before ranking, this deepens
`capital_allocation` queries substantially while leaving `pricing`, `m_and_a`, `key_hire` and
`product_sunset` untouched at 5 cases each.

**Pattern concentration.** Ten of the cases are activist short theses. They are genuinely
distinct decisions with different failure modes, but a `capital_allocation` query may retrieve
several at once and present a narrower range of decision shapes than the domain actually spans.

Correcting these would require deliberately sourcing documented failures and non-events, which
this directory structurally does not contain.
