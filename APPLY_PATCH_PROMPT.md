# Claude Code prompt — apply the overnight patch

Save `fraudlens-overnight-patch.zip` next to your `fraudlens/` folder, open Claude
Code in the **parent** directory, and paste the block below.

---

I have `fraudlens-overnight-patch.zip` in this directory and my existing project in
`fraudlens/`. The zip contains an overnight pass on the same project: four new
analysis scripts, a restyled dashboard, and two bug fixes in existing files.

Do this:

1. Unzip it to a temp directory (NOT over my project yet) and read
   `fraudlens/CHANGES.md` inside it. That file explains every change.

2. Show me a diff summary before touching anything — which files are new, which
   are modified, and for each modified file roughly what changed. These four are
   modifications to existing code, so I want to see them:
   - `dashboard/src/App.jsx`        (two bug fixes)
   - `dashboard/src/styles.css`     (light theme tokens + two correction blocks appended)
   - `dashboard/src/risk.js`        (risk colour ramp replaced)
   - `dashboard/src/components/MapView.jsx` (map fill/stroke colours)

   Everything else is new and safe to copy: `impact.py`, `find_case.py`,
   `deck_charts.py`, `build_deck.py`, `qa_geom.py`, and files under `docs/`.

3. If I have uncommitted work in those four files, stop and tell me instead of
   overwriting. Otherwise copy all the files into `fraudlens/`, preserving paths.

4. Then verify, in this order, and report what fails:

   ```
   cd fraudlens
   source venv/bin/activate          # or however I activate my env
   python -m features.test_leakage   # must print LEAKAGE TEST PASSED
   python -m model.evaluate          # docs/metrics.md must be unchanged vs git
   python impact.py                  # writes docs/impact.md
   python find_case.py               # writes docs/deck_case.json
   python deck_charts.py             # writes the two deck charts
   python build_deck.py && python qa_geom.py   # must report "issues: 0"
   ```

   `docs/metrics.md` must come out byte-identical to what git already has — if it
   does not, something in the model path was disturbed and I want to know.

5. Then start the app and confirm the two bug fixes by hand:

   ```
   uvicorn api.main:app --port 8000        # terminal 1
   cd dashboard && npm run dev             # terminal 2
   ```

   - **Bug 1** — as I4C Admin, click any district to open the right-hand panel,
     then switch to State LEA. The panel must CLOSE. Before the fix it stayed
     open showing an out-of-jurisdiction district.
   - **Bug 2** — as State LEA with a state selected (try Jharkhand), every
     district outside that state must be greyed out on the map. Before the fix
     the whole country stayed coloured.

6. Report anything that looks wrong. Do not commit — I will review and push myself.

---

## If you would rather do it by hand

```bash
unzip fraudlens-overnight-patch.zip -d patch
cat patch/fraudlens/CHANGES.md

# see what actually differs before overwriting
for f in dashboard/src/App.jsx dashboard/src/styles.css dashboard/src/risk.js \
         dashboard/src/components/MapView.jsx; do
  echo "=== $f ==="; diff -u "fraudlens/$f" "patch/fraudlens/$f" | head -60
done

# apply
cp -r patch/fraudlens/. fraudlens/

# verify
cd fraudlens
python -m features.test_leakage
python impact.py && python deck_charts.py
python build_deck.py && python qa_geom.py
```
