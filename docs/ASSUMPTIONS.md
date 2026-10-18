# Assumptions and fallbacks

Judgment calls, proxies, data-source failures and the fallbacks used are recorded here before work continues past them (rule 7).

## Fixed design decisions
- DUK is an EIA balancing authority (most of NC plus upstate SC), far larger than NC-08. Zone demand is therefore estimated, never observed. (Detailed in Phase 2.)
- Harm weights `w_s = 0.7`, `w_e = 0.3` are judgment calls, varied in the sensitivity panel.
- Outage duration `h = 1` is a judgment call.
- Banned/required vocabulary is enforced by a lint test (Phase 4).

## Harm model formula
TBD Phase 4: full formula, symbols, sources, normalization, missing-data rules, worked single-zone example.

## Data-source failures and fallbacks
None yet.
