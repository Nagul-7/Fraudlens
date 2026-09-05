# FraudLens - 3-minute demo script

**Before you start.** Both servers running, browser at `http://localhost:5173`,
clock reset to 01 Nov 2025 00:00, role on **I4C Admin**, threshold **80%**,
top-K **25**. Full screen, 1920x1080.

```bash
# terminal 1
source venv/bin/activate && uvicorn api.main:app --port 8000
# terminal 2
export PATH=$HOME/.local/opt/node20/bin:$PATH
cd dashboard && npm run dev
# then, to reset between run-throughs
curl -X POST http://127.0.0.1:8000/simulate/reset
```

Timings below are cumulative. If you are running long, cut step 6 (bank role)
and shorten step 8 — never cut step 3 or step 9.

---

## 1. The problem (0:00 - 0:25)

*Do:* stay on the map, do not click anything yet.

> "When someone is defrauded online, the money doesn't disappear. It runs
> through a chain of mule accounts for a few hours, and then somebody withdraws
> it as cash from an ATM — typically two to forty-eight hours later, in a
> district hundreds of kilometres from the victim.
>
> That gap is the only window anyone has to intervene. Today it's used to file
> paperwork. We use it to predict where the cash is about to come out."

---

## 2. The map (0:25 - 0:50)

*Do:* gesture across the map, then to the legend, then the left watchlist.

> "This is all 724 districts of India, coloured by the predicted probability
> that a fraud cash-out happens there in the next six hours. Most of the country
> is quiet — on any given window only about five percent of districts see one.
> That's the whole point: a police force can't watch 724 districts, so our job
> is to say which twenty-five to watch tonight.
>
> That's the watchlist on the left, ranked."

---

## 3. Advance the clock — the self-grading moment (0:50 - 1:25)

**This is the centrepiece. Do not rush it.**

*Do:* click **Advance 6h**. Wait for the top bar to flash. Then click it twice
more, pausing on each result.

> "I'll advance the simulated clock by one six-hour window. The model rescores
> every district...
>
> — and look at the top bar. It just graded the window that *closed*. It flagged
> nine districts; nine of them actually had a fraud cash-out. That's not a
> number we computed in advance and put on a slide — the system is marking its
> own homework, live, against ground truth."

*Do:* advance twice more.

> "Again. And again. This is running on months the model has never seen — the
> API physically refuses to serve a window from the training period. If you ask
> it for June, it returns an error."

---

## 4. District drill-down and reason codes (1:25 - 1:55)

*Do:* click the top district in the watchlist (usually Deoghar, Jharkhand).

> "Click any district and you get the case for it. Risk, national rank — and
> critically, *why*. These three reasons come from the model's own feature
> contributions for this specific district, not a template: fifty-one mule
> accounts here are holding money right now; eight point four lakh across
> thirty-one active chains; the last cash-out here was minutes ago.
>
> Underneath, the actual chains — complaint number, fraud type, amount held, how
> old the chain is. Anything in the eight-to-twenty hour band is amber, because
> the median time from fraud to first withdrawal is about fourteen hours. Those
> are the ones about to move."

---

## 5. State LEA and the coordination gap (1:55 - 2:25)

*Do:* switch role to **State LEA**, pick **Jharkhand**.

> "Now sign in as a state agency. The map dims — Jharkhand only. The alert feed
> drops from forty-nine alerts to six. That's not the UI hiding things; the
> server never sent the others. Role-based segregation is a legal requirement,
> not a feature.
>
> But here's the part that matters." *(point to the cross-jurisdiction inbox)*
> "These are complaints filed **in** Jharkhand whose money has already left the
> state. Eleven chains, one point three lakh, heading into West Bengal, Uttar
> Pradesh, Maharashtra.
>
> Jharkhand took these complaints and can't act where the money is. West Bengal
> has no idea a Jharkhand case is about to land on it. That's the coordination
> gap in the problem statement, and this is the referral that closes it — look
> at that one going into a West Bengal district our own model rates above
> ninety-nine percent for the next six hours."

---

## 6. Bank role (2:25 - 2:40)

*Do:* switch role to **Bank / FI**, pick any bank.

> "And a bank sees something completely different. No alerts, no reason codes,
> no district rankings — the left panel says the national view is withheld, and
> the map only shows districts where this bank actually operates ATMs.
>
> What it does get is operational: its own accounts holding fraud money right
> now, with a CFCFRMS freeze recommendation on each. Enough to act, nothing
> about anyone else's case."

---

## 7. Intelligence report (2:40 - 2:55)

*Do:* switch back to **I4C Admin**, open the bell, click **Report** on an alert
with money in flight.

> "Every alert opens as a document an officer can actually file. Reference
> number, the window, evidence as numbered findings with the weight each one
> carried, the funds held, the ATMs to cover, recommended action.
>
> Look at the origin column — money in this one Jharkhand district came from
> Haryana, Odisha, Maharashtra, Tamil Nadu, ten states. That's the whole problem
> on one page. And it prints."

*Do:* click **Print / Save as PDF** if time allows, otherwise just say it.

---

## 8. Metrics (2:55 - 3:10)

> "On the held-out months: watching twenty-five districts a window catches
> fifty-seven percent of the districts that actually had a cash-out. A static
> hotspot list gets twenty-two. Perfect prediction would get seventy-three, so
> we're at about three-quarters of what's achievable.
>
> The features that do the work are the live-chain ones — money sitting in
> accounts right now. They're sixty percent of the model's gain, and removing
> them costs thirteen points at K equals fifty, because they catch districts
> with no recent history at all."

---

## 9. The honest close (3:10 - 3:30)

**Never cut this. It is the most credible thing you will say.**

> "One thing to be clear about: this data is synthetic. We built a generator
> that encodes documented fraud behaviour — the Jamtara-style corridors, the
> mule chains, structuring under fifty thousand, corridors drifting monthly as
> police pressure moves. These numbers prove the pipeline learns those patterns
> end to end. They are not a claim about real-world accuracy, and we're not
> going to pretend otherwise.
>
> What we'd argue is that the hard part is done. The feature pipeline already
> consumes a complaint-and-transaction-trail shape, and it already models the
> fact that you can't see a trail until the complaint is filed. Swapping the
> generator for a real CFCFRMS feed is a connector, not a rewrite."

---

## Likely questions

**"How do we know it isn't just memorising the hotspots?"**
> Corridors drift every month in the generator, and the static-watchlist
> baseline is our comparison precisely because a memorised list scores
> twenty-two percent. On districts that only became hotspots during the test
> months, we get sixty-four percent and the static list gets forty-six.

**"Is the segregation real or cosmetic?"**
> Server-side. Run `curl "localhost:8000/feed?role=BANK&bank=SBI"` and the
> response has no alerts in it at all. There's nothing in the payload to
> un-hide.

**"Why six-hour windows?"**
> It matches the operational unit — a shift — and the cash-out timing. Median
> fraud-to-withdrawal is fourteen hours, so a six-hour window gives roughly two
> chances to intervene before the money is gone.

**"What's the false-positive cost?"**
> At K equals twenty-five, precision is seventy-seven percent: about six of the
> twenty-five districts watched see nothing. The threshold slider moves that
> trade-off, and because the probabilities are calibrated, eighty percent on the
> slider genuinely means about eighty percent.

## Recovery

- **Blank or broken panel:** reload. An error boundary catches render failures
  and offers a reload rather than a white screen.
- **"Cannot reach the API":** the backend died. Restart uvicorn; the page has a
  Retry button.
- **Feed empty:** you reset the clock. Advance three times to regenerate alerts.
- **Wrong role state:** the switcher clears the feed, report and toasts on every
  role change, so just switch again.
