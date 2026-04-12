# MuniRevenue Visualization — Open Questions

**Status:** Outline — seed file for implementation agents. Running log, amended weekly.
**Companion to:** `docs/visualization-master-plan.md` §19.7.

## Process
1. New questions are added as PR comments and promoted here at weekly review.
2. Each question has an owner and a target decision date.
3. Decided questions stay in the file with their resolution for historical reference.
4. Questions that block a Phase 1 item take priority in the weekly triage.

## Schema
| Col | Meaning |
|---|---|
| `id` | Stable reference (Q01, Q02, ...) |
| `area` | `design` / `data` / `backend` / `frontend` / `product` / `legal` / `ops` |
| `question` | Plain-language question |
| `raised_by` | Person or doc |
| `target_date` | Target decision date |
| `decision` | Resolution, once decided |
| `decided_by` | Decider |
| `notes` | Context + link to PR / issue |

## Open (seed set)

| id | area | question | target | notes |
|---|---|---|---|---|
| Q01 | data / legal | Is there an OK county TopoJSON licence-compatible with a commercial site? (needed for choropleth in Phase 2) | Week 6 | Candidates: US Census TIGER/Line (public domain), naturalearthdata (public domain); need to simplify to ≤ 40 KB |
| Q02 | legal / ops | Are suppression rules contractually documented with OTC? Do we need to display a legal notice? | Week 4 | Affects every chart footer + methodology page |
| Q03 | product | Which auth tier gates saved views / watchlists? Free, logged-in, or paid? | Week 10 | Phase 4 dependency |
| Q04 | design | Do we need a printable "council packet" template with per-city branding? | Week 12 | Affects chart-pack service complexity |
| Q05 | product | Who maintains event annotations — admin-only or user-submitted? | Week 12 | Moderation burden if user-submitted |
| Q06 | data | Are NAICS 6-digit breakdowns complete enough in `mv_top_naics_by_city` for drill-through, or is there a long-tail gap? | Week 7 | Run coverage SQL before Phase 2 treemap ships |
| Q07 | backend | How far back should peer groups be re-computed historically? (e.g., only 2020+ or full 2010+) | Week 11 | Affects `mv_peer_group_metrics` size |
| Q08 | product | Should forecast variance bars use the selected model or the ensemble? | Week 8 | Currently `selected_model` in `forecast_runs` |
| Q09 | product | Do we ship a public API token tier for analysts before or after watchlist? | Week 12 | Affects account UI roadmap |
| Q10 | ops | Is server-side chart-pack PDF rendering worth the ops complexity vs. client-side? | Week 14 | Client-side via pdf-lib is the Phase 4 default |
| Q11 | design | Red / green is banned — confirm warm-orange for negatives is the final call with the founder | Week 2 | Affects every chart built from Week 1 onward |
| Q12 | design | Default time horizon on city overview — 24 months, 36 months, or 60 months? | Week 3 | Affects default URL state |
| Q13 | frontend | How do we handle the existing `localStorage('munirev:lastCity')` vs URL-based state? Merge or deprecate? | Week 2 | Affects `frontend/src/state/filters.ts` design |
| Q14 | backend | Should the contribution endpoint support `level=county` day one or ship city-first? | Week 9 | Phase 2 scope decision |
| Q15 | product | Exec vs analyst mode — should it be per-user or per-session? | Week 6 | Affects `user_profile_preferences` |
| Q16 | data | Are we comfortable showing preliminary figures on the public overview, or only to logged-in users? | Week 4 | Affects trust framing |

## Decided (empty — to be filled as decisions land)

| id | decision | decided_by | date |
|---|---|---|---|

## Parking lot (ideas with no urgency)
- Mobile-native app.
- Voice narration of narrative callouts.
- Comparison to BLS county employment series on city view.
- Public API with rate limit tier.
