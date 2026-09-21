# Claude Code prompt — apply the patch and fix what you found

Paste everything below the line into Claude Code, opened in the folder that
contains both `~/Desktop/Fraudlens/` and the patch zip.

---

Apply it — with these fixes in the same pass. You found real problems in that
patch; this is the go-ahead to integrate it and correct them. Leave everything
uncommitted for me to review.

## 0. Use the right zip first

There are several `fraudlens-overnight-patch.zip` downloads. Use the NEWEST one.
Confirm it contains `fraudlens/find_case.py` and `fraudlens/APPLY_PATCH_PROMPT.md`.
If it doesn't, it's an old version — stop and tell me. (The version you tested
earlier was an old one: its `build_deck.py` had no dataset block and no link
slots.)

## 1. Apply the patch

Copy the zip's `fraudlens/` contents into `~/Desktop/Fraudlens/` — merge, never
delete anything. If any of these four have uncommitted changes, stop and show me
first: `dashboard/src/App.jsx`, `dashboard/src/styles.css`, `dashboard/src/risk.js`,
`dashboard/src/components/MapView.jsx`.

## 2. MUST FIX — /heatmap leaks out-of-scope risk (your item 1)

This matters most: two claims in the deck are false until it's fixed.

**Server side (`api/main.py`):**
- `/heatmap` should accept `role`, `state_name` and `bank` query params, the same
  way `/feed`, `/cross-jurisdiction` and `/bank/exposure` already do.
- `role=STATE`: return only districts in `state_name`. A `state` filter must never
  widen that.
- `role=BANK`: return only that bank's footprint districts. Reuse whatever
  `/bank/exposure` uses to compute `own_district_ids` — don't write a second version.
- `role=I4C`, or no role: keep the current behaviour.

**Client side (`dashboard/src/App.jsx`):**
- Always send the role params to `/heatmap`.
- The unscoped `allScores` fetch (around line 79) must only run for I4C. For
  STATE and BANK, build `riskById` from the scoped response only.
- When a State LEA hovers a district outside their state, the tooltip reads
  "Outside your jurisdiction". For a Bank, it reads "Outside your footprint".
  Show a label, not a number.
- **Don't reintroduce the "risk --" tooltip bug** that commit 5c9437b fixed. Keep
  the `riskRef` pattern: for I4C every district still has to show a real score.

**Add a test** — `tests/test_segregation.py` or similar — that calls `/heatmap`
with `role=STATE&state_name=Jharkhand` and asserts that no returned district is
outside Jharkhand. Also add the Bank equivalent. This makes the deck's claim
something a test proves, not something we just assert.

**Check by hand:** as a Jharkhand State LEA, the `/heatmap` request carries the
role params, the response has only Jharkhand's 24 districts, and hovering West
Bengal says "Outside your jurisdiction". As Bank/Axis, hovering outside the
footprint says "Outside your footprint". As I4C, all 724 districts still show
real scores.

**Fallback, only if this can't be done in time:** don't leave the deck making
false claims. Reword slide 4's risk card ("…enforced on the server, so each user
sees only what they are entitled to") and slide 5's Bank card ("No crime
intelligence is shared") so they describe only what's actually true. Tell me if
you had to use this.

## 3. MUST FIX — unreadable text and dead CSS (your item 2)

- For every selector in the two light-theme correction blocks at the end of
  `styles.css`, grep the JSX for that class name. Delete every selector that
  matches nothing. Don't try to guess what was intended — the last pass guessed,
  and that's where the dead rules came from.
- Give the real classes readable light-theme colours: `.segregation-box`,
  `.freeze-rec`, `.err-box`, `.scope-chip`, `.bell-badge`, `.watch-item`. The
  Bank "Restricted view" notice is the one you flagged.
- Text contrast must be at least 4.5:1 against its own background. Compute it;
  don't eyeball it.

## 4. MUST FIX — make build_deck.py portable (your item 3)

- Replace the hardcoded `SRC`, `OUT` and `DOCS` paths with paths relative to the
  repo (`Path(__file__).resolve().parent`).
- The script builds from an SIH template deck. Copy one into the repo as
  `templates/sih2026_template.pptx` — the team's original
  `The_PixelRex_Crew-2.pptx` if it's on this machine, otherwise a copy of the
  latest `FraudLens_SIH2026_PixelRex.pptx`. Either works, because the script keeps
  only the template's chrome, matched by shape name.
- Write the output to a new file, `build/FraudLens_SIH2026_PixelRex.pptx`.
  **Never read from or write to anything in ~/Downloads.** LibreOffice has the
  Downloads deck open, and I'll compare the two by hand.
- Add `python-pptx` to `requirements.txt`. Check that `matplotlib` and `Pillow`
  are there too, since `deck_charts.py` and `find_case.py` need them.
- The same hardcoded-path problem may exist in `impact.py`, `deck_charts.py`,
  `find_case.py` and `qa_geom.py` — check and fix all of them.

## 5. SHOULD FIX — State LEA sidebar clipping (your item 4)

The referral inbox covers the "Watchlist size" section in the State LEA left
panel. That section should stay reachable: give the panel proper scrolling or
room. This bug existed before the patch — fix it only if 2–4 are done.

## 6. Rebuild and verify

In this order. Report every failure:

```
python -m features.test_leakage   # LEAKAGE TEST PASSED
python -m model.evaluate          # docs/metrics.md byte-identical to git
pytest tests/                     # including the new segregation test
python impact.py
python find_case.py
python deck_charts.py
python build_deck.py && python qa_geom.py   # issues: 0
```

Then regenerate the dashboard screenshots the deck uses —
`docs/ui_national.png` and `docs/ui_district.png` — from the fixed app at
1920×1080 (Playwright if it's available). Rebuild the deck once more so it picks
them up, and check `qa_geom.py` again.

## 7. Report back

- One line per item above: fixed, fallback used, or skipped (and why).
- Before/after screenshots for items 2 and 3 in `scratchpad/`.
- Anything in the deck that is still not literally true.
- Don't commit anything.
