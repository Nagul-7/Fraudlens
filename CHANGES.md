# What changed — overnight pass before SIH idea submission

Drop these files over your existing `fraudlens/` checkout. Nothing else was touched.

## New analysis

| File | What it does |
|---|---|
| `impact.py` | Converts the ranking into rupees and hours. Same test split and same top-K rule as `model/evaluate.py`. Writes `docs/impact.md` + `docs/impact.json`. |
| `deck_charts.py` | Builds the two deck charts from the same numbers. |
| `build_deck.py` | Rebuilds the 6-slide PPTX from the official SIH template. |
| `qa_geom.py` | Geometry check on the built deck — overflow past the safe area, picture/card overlaps. |
| `find_case.py` | Picks one real, typical inter-state case from the held-out test months for slide 5. Writes `docs/deck_case.json`. |

Run order (the API does not need to be running):

    python impact.py
    python find_case.py
    python deck_charts.py
    python build_deck.py && python qa_geom.py

## Headline numbers these produce

Held-out test months, synthetic world, Rs 124.4 crore withdrawn in total.

| Watchlist | FraudLens | Past-week heat map | Gap |
|---|---|---|---|
| Top 10 | Rs 50.6 cr (40.7%) | Rs 35.5 cr (28.5%) | +Rs 15.1 cr |
| Top 25 | Rs 89.9 cr (72.2%) | Rs 84.9 cr (68.3%) | +Rs 5.0 cr |
| Top 50 | Rs 110.6 cr (88.9%) | Rs 91.5 cr (73.5%) | +Rs 19.1 cr |

Warning before the first rupee leaves a flagged district: median 22–78 minutes
depending on K. Modest, and stated as such. The number that matters
operationally is that 82% of the flagged money is still inside the network one
hour after the alert, 64% after two.

## Two real bugs fixed in `dashboard/src/App.jsx`

1. **Stale panel across a role switch.** The open district was cleared only for
   the Bank role. Sign in as I4C, open any district, switch to a State LEA, and
   that district's full intelligence panel stayed on screen — including when it
   sat outside the state's jurisdiction. The server was never fooled, but a
   stale panel a user cannot distinguish from a live one is exactly what role
   segregation exists to prevent. Now cleared on any role or jurisdiction change.

2. **State LEA saw the national map.** `visibleIds` tested `filters.state`, but a
   State LEA's jurisdiction comes from `role.stateName` — the dropdown only
   displays it, locked. So the map fell through to "nothing dimmed" and painted
   every district in the country, while every panel beside it was correctly
   scoped. Fixed; the map now dims everything outside the jurisdiction.

Both were visible in screenshots headed for the deck, and the second directly
contradicted the deck's own claim about server-side segregation.

## Dashboard restyle

`styles.css`, `risk.js`, `MapView.jsx`.

- Warm, paper-like light theme replacing the dark console. Tokens live in
  `:root`; two correction blocks at the end of `styles.css` handle the rules that
  were written against the old dark surface.
- **The risk ramp is now sequential — one hue, light to dark — not a
  green-to-red rainbow.** Risk is a magnitude, and magnitude is read from
  lightness; a rainbow asks the reader to decode hue order, and green-vs-red is
  the one pair red-green colourblind officers cannot separate. Quiet districts
  now sit close to the page colour and the eye lands on the live corridors.

Screenshots for the deck are in `docs/ui_*.png`, captured from the running app.

## Slide 5 case study — what it is and is not

The incident log on slide 5 is a real complaint, chain and cash-out from the
held-out test months of the synthetic world — complaint #95690, East Singhbhum
to Rewari. `find_case.py` selects it as a *typical* case (UPI or card, ordinary
amount, ordinary chain depth, at least an hour of warning), not the best one.

It sits behind two figures on that slide:

- **2 in 3** — of 10,898 inter-state chains that cashed out in the test months,
  7,218 (66.2%) landed in a district already on FraudLens's top-25 for that window.
- **Rs 16 cr per hour** — the flagged money still in accounts falls from Rs 90 cr
  to 74, 58 and 42 cr at 0, 1, 2 and 3 hours: drops of 16.0, 15.9 and 15.6.

Deliberately **not** used: the share of chains that cross a state line (92%).
That is a property of how the simulator places cash-outs, not a finding, and
presenting it as one would mislead.
