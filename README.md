# Conquest Scenario Planner

What-if tool for the Stability Conquest event (July 17–26, 2026): enter completion
counts per team per territory, see ownership / region control / points under the
original ruleset, and get a ranked "what should we grind next" list by points per hour.

## Run locally

```
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Live data

The app syncs from the stabilisite-backend API **automatically when it opens**:
it detects the active conquest event (`/v2/events/active`, falling back to the
built-in event ID) and pulls regions, tasks, batch quantities, team names, and
live completion counts per team. Refreshing the browser (F5) starts a fresh
session and re-syncs; the sidebar **🛰️ Live data** panel re-syncs mid-session.
If the API is unreachable, the app falls back to the embedded draft task list
and shows a warning — everything still works offline.

- Sync **replaces** the board with the live event structure. Save a scenario
  first if you have manual what-ifs you want to keep.
- Hour estimates come from `hours.json` (committed next to app.py), overridden
  by any edits you make in the Task Hours tab this session. Tasks with no
  entry get a 5.0h default and a ⚠️ flag — set their hours in the Task Hours
  tab, then **⬇️ Download hours.json** there and commit it so every visitor
  gets the corrected estimates.

## Share with your co-captain

Option A (simplest): both run it locally and swap scenario files — the sidebar
**Save scenario** button downloads a `.json` you can drop in Discord; the other
person loads it with the sidebar uploader.

Option B (hosted link): push this folder to a GitHub repo, then deploy free at
https://share.streamlit.io (New app → pick the repo → main file `app.py`).
Note: session state on the hosted app is per-browser-tab and resets on refresh,
so still use Save scenario to keep anything you care about.

## How scoring works (original ruleset, all values editable in the sidebar)

- Territory: strict-most completions owns it (ties = contested, no owner) — 3 pts each
- Region: strict-most territories leads it — 20 pts normal, 30 pts raid (⭐ Desert/Morytania/Kourend)
- Region sweep (green-log 5/5) bonus: value TBD, defaults to 0
- Superlatives (Globetrotter, Raid Purples/Pets): set placements manually on the
  Scoreboard tab — 20/12/6

## Notes

- Task list, batch quantities, and hours come from the draft
  (`conquest_task_list - Task List.csv`); ⚠️ marks unverified rates. Hours are
  editable on the Task Hours tab and are saved into scenario files.
- The Priorities tab's "Pts gained" simulates the flip, so it includes region
  flips and sweeps the take would cause, not just the 3 territory points.
