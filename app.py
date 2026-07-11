"""Conquest Scenario Planner — territory/points what-if tool for the Stability Conquest event.

Run:  py -m streamlit run app.py
"""

import copy
import difflib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Conquest Scenario Planner", page_icon="⚔️", layout="wide")

# ---------------------------------------------------------------------------
# Default event data (from conquest_task_list - Task List.csv). Used until a
# live sync or scenario load replaces it. hrs = estimated solo hours PER
# COMPLETION (one batch). "unv" = ⚠️ needs verification — treat as rough.
# ---------------------------------------------------------------------------

DEFAULT_REGIONS = [
    {"name": "Misthalin / Wilderness", "raid": False, "tasks": [
        {"name": "Ancient emblem / Rev weapon", "qty": 5, "hrs": 9.1, "unv": False},
        {"name": "Larran's Key", "qty": 10, "hrs": 3.3, "unv": False},
        {"name": "Dragon Pickaxe", "qty": 1, "hrs": 12.5, "unv": True},
        {"name": "Corp Beast Unique", "qty": 1, "hrs": 6.0, "unv": False},
        {"name": "Tormented Demon Unique", "qty": 1, "hrs": 5.0, "unv": True},
    ]},
    {"name": "Asgarnia", "raid": False, "tasks": [
        {"name": "Bandos or Armadyl Unique", "qty": 1, "hrs": 13.0, "unv": False},
        {"name": "Saradomin or Zamorak Unique", "qty": 1, "hrs": 13.0, "unv": False},
        {"name": "Nex Unique (incl. pet)", "qty": 1, "hrs": 14.0, "unv": False},
        {"name": "Cerberus Unique", "qty": 1, "hrs": 2.0, "unv": True},
        {"name": "Whisperer Unique", "qty": 3, "hrs": 4.0, "unv": False},
    ]},
    {"name": "Kandarin / Karamja", "raid": False, "tasks": [
        {"name": "Kraken Unique", "qty": 3, "hrs": 9.0, "unv": False},
        {"name": "Thermy Unique", "qty": 1, "hrs": 5.0, "unv": False},
        {"name": "Zenyte Shard", "qty": 2, "hrs": 8.7, "unv": False},
        {"name": "Infernal Cape", "qty": 1, "hrs": 1.5, "unv": True},
        {"name": "Penance Queen KC", "qty": 25, "hrs": 2.0, "unv": True},
    ]},
    {"name": "Fremennik", "raid": False, "tasks": [
        {"name": "Dagannoth Ring", "qty": 3, "hrs": 5.0, "unv": False},
        {"name": "Vorkath Points", "qty": 3, "hrs": 6.7, "unv": False},
        {"name": "Venator Shard", "qty": 1, "hrs": 4.0, "unv": False},
        {"name": "Duke Unique", "qty": 1, "hrs": 7.5, "unv": True},
        {"name": "Duke Awakener's Orb", "qty": 3, "hrs": 4.3, "unv": False},
    ]},
    {"name": "Desert", "raid": True, "tasks": [
        {"name": "⭐ TOA: Lightbearer or Fang", "qty": 1, "hrs": 25.0, "unv": False},
        {"name": "TOA: Masori, Ward or Shadow", "qty": 1, "hrs": 20.0, "unv": False},
        {"name": "Leviathan Awakener's Orb", "qty": 3, "hrs": 6.7, "unv": False},
        {"name": "Tempoross Unique", "qty": 1, "hrs": 7.5, "unv": True},
        {"name": "GOTR Unique", "qty": 1, "hrs": 6.0, "unv": True},
    ]},
    {"name": "Morytania", "raid": True, "tasks": [
        {"name": "⭐ TOB Purple (Avernic etc.)", "qty": 1, "hrs": 21.7, "unv": False},
        {"name": "Non-Avernic TOB drop", "qty": 5, "hrs": 15.0, "unv": True},
        {"name": "Araxxor or GG Unique", "qty": 1, "hrs": 4.0, "unv": True},
        {"name": "Nightmare or Phosani's Unique", "qty": 1, "hrs": 15.0, "unv": False},
        {"name": "Barrows Unique", "qty": 4, "hrs": 4.0, "unv": False},
    ]},
    {"name": "Tirannwn", "raid": False, "tasks": [
        {"name": "Zulrah Unique", "qty": 1, "hrs": 3.2, "unv": False},
        {"name": "Crystal Weapon/Armour Seed", "qty": 1, "hrs": 3.6, "unv": False},
        {"name": "Gwenith Glide Laps", "qty": 40, "hrs": 6.7, "unv": False},
        {"name": "Crystal Teleport Seed", "qty": 4, "hrs": 4.0, "unv": True},
        {"name": "Zalcano Points", "qty": 100, "hrs": 2.0, "unv": False},
    ]},
    {"name": "Kourend", "raid": True, "tasks": [
        {"name": "⭐ COX Prayer Scroll", "qty": 1, "hrs": 25.0, "unv": True},
        {"name": "COX Non-Scroll Purple", "qty": 2, "hrs": 12.0, "unv": True},
        {"name": "Molch Uniques", "qty": 10, "hrs": 5.0, "unv": True},
        {"name": "Hydra or Unsired", "qty": 1, "hrs": 12.5, "unv": True},
        {"name": "Yama Unique", "qty": 1, "hrs": 13.5, "unv": False},
    ]},
    {"name": "Varlamore", "raid": False, "tasks": [
        {"name": "Vardorvis Points / Orb", "qty": 3, "hrs": 7.5, "unv": True},
        {"name": "Moons of Peril Unique", "qty": 3, "hrs": 3.0, "unv": False},
        {"name": "Doom Unique", "qty": 1, "hrs": 8.0, "unv": True},
        {"name": "Colosseum Unique", "qty": 2, "hrs": 10.0, "unv": True},
        {"name": "Hunter Rumour Completion", "qty": 12, "hrs": 6.5, "unv": True},
    ]},
]

N_TEAMS = 4
SUPERLATIVES = ["Globetrotter (most unique tasks)", "Raid Purples / Pets"]
PLACES = ["1st", "2nd", "3rd"]

# Live backend (stabilisite-backend on Railway). Regions containing these
# words score as raid regions (⭐).
DEFAULT_API_URL = "https://stability-backend-prototypes-production.up.railway.app"
DEFAULT_EVENT_ID = "8986ee4e-e5e2-4d55-ad99-b9f26436a14e"
RAID_REGION_WORDS = ("desert", "morytania", "kourend")
TEAM_FALLBACK_COLORS = ["#3B82F6", "#EF4444", "#22C55E", "#EAB308"]
NEUTRAL_COLOR = "#8a8a8a"
DEFAULT_HRS = 5.0  # hours for live tasks with no name match anywhere
HOURS_FILE = "hours.json"  # curated {task name: hrs}, committed next to app.py


def task_id(ri, ti):
    return f"{ri}.{ti}"


def build_tasks(regions):
    return [
        (task_id(ri, ti), ri, region, task)
        for ri, region in enumerate(regions)
        for ti, task in enumerate(region["tasks"])
    ]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def init_state():
    ss = st.session_state
    ss.setdefault("regions", copy.deepcopy(DEFAULT_REGIONS))
    tasks = build_tasks(ss.regions)
    ss.setdefault("counts", {tid: [0] * N_TEAMS for tid, *_ in tasks})
    ss.setdefault("hours", {tid: t["hrs"] for tid, _, _, t in tasks})
    ss.setdefault("team_names", ["Team 1", "Team 2", "Team 3", "Team 4"])
    ss.setdefault("team_colors", list(TEAM_FALLBACK_COLORS))
    ss.setdefault("supers", {s: {p: "—" for p in PLACES} for s in SUPERLATIVES})
    # Incumbent holders from the live event (backend rule: a holder keeps a
    # territory/region until a challenger STRICTLY exceeds them).
    ss.setdefault("base_owners", {})          # {tid: team index or None}
    ss.setdefault("base_region_owners", [])   # [team index or None] per region
    ss.setdefault("base_counts", {})          # counts as synced (owner is live-exact until edited)
    ss.setdefault("epoch", 0)  # bumped on load/reset to remount data editors
    ss.setdefault("loaded_file", None)
    ss.setdefault("live_summary", None)
    ss.setdefault("live_error", None)
    ss.setdefault("did_startup_sync", False)


init_state()
SS = st.session_state


def scenario_json():
    return json.dumps({
        "regions": SS.regions,
        "counts": SS.counts,
        "hours": SS.hours,
        "team_names": SS.team_names,
        "supers": SS.supers,
        "base_owners": SS.base_owners,
        "base_region_owners": SS.base_region_owners,
        "base_counts": SS.base_counts,
        "config": {k: SS[k] for k in CONFIG_KEYS if k in SS},
    }, indent=1)


def load_scenario(data):
    if "regions" in data:
        SS.regions = data["regions"]
    SS.base_owners = data.get("base_owners", {})
    SS.base_region_owners = data.get("base_region_owners", [])
    SS.base_counts = data.get("base_counts", {})
    tasks = build_tasks(SS.regions)
    SS.counts = {tid: [0] * N_TEAMS for tid, *_ in tasks}
    SS.hours = {tid: t["hrs"] for tid, _, _, t in tasks}
    for tid, *_ in tasks:
        if tid in data.get("counts", {}):
            SS.counts[tid] = ([int(x) for x in data["counts"][tid]] + [0] * N_TEAMS)[:N_TEAMS]
        if tid in data.get("hours", {}):
            SS.hours[tid] = float(data["hours"][tid])
    if "team_names" in data:
        SS.team_names = (list(data["team_names"]) + [f"Team {i+1}" for i in range(N_TEAMS)])[:N_TEAMS]
        for i, name in enumerate(SS.team_names):
            SS[f"tn_{i}"] = name  # widget state would otherwise win over the new names
    for s in SUPERLATIVES:
        if s in data.get("supers", {}):
            SS.supers[s] = data["supers"][s]
    for k, v in data.get("config", {}).items():
        if k in CONFIG_KEYS:
            SS[k] = v
    for si, s in enumerate(SUPERLATIVES):
        for p in PLACES:
            SS[f"sup_{si}_{p}"] = SS.supers[s].get(p, "—")
    SS.epoch += 1


# ---------------------------------------------------------------------------
# Live sync (stabilisite-backend /v2 conquest endpoints)
# ---------------------------------------------------------------------------

_STOP_WORDS = {"any", "unique", "uniques", "the", "or", "of", "a", "incl",
               "pet", "drop", "drops", "x", "s", "kc", "points"}


def _name_tokens(name):
    words = re.findall(r"[a-z0-9]+", name.lower().replace("⭐", "").replace("⚠️", ""))
    return set(w for w in words if w not in _STOP_WORDS) or set(words)


def _tokens_match(x, y):
    # equal, close spelling (Leviathin/Leviathan), or prefix (Corp/Corporeal)
    if x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.85:
        return True
    shorter, longer = (x, y) if len(x) <= len(y) else (y, x)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _token_overlap(a, b):
    hits = sum(1 for x in a if any(_tokens_match(x, y) for y in b))
    return hits / len(a | b)


def _carry_hours(live_name, old_hours_by_name):
    """Best-effort fuzzy match of a live task name to a known task's hour estimate."""
    best_hrs, best_score = None, 0.0
    tokens = _name_tokens(live_name)
    for old_name, hrs in old_hours_by_name.items():
        other = _name_tokens(old_name)
        if ("non" in tokens) != ("non" in other):
            continue  # "Avernic" and "Non-Avernic" are opposite tasks
        score = _token_overlap(tokens, other)
        if score > best_score:
            best_hrs, best_score = hrs, score
    if best_score >= 0.34:
        return best_hrs, True
    return DEFAULT_HRS, False


def _load_hours_file():
    try:
        with open(HOURS_FILE, encoding="utf-8") as f:
            return {str(k): float(v) for k, v in json.load(f).items()}
    except Exception:
        return {}


def _resolve_hours(name, session_hours, file_hours):
    """Session edits win, then the committed hours.json, then fuzzy match, then default."""
    if name in session_hours:
        return session_hours[name], True
    if name in file_hours:
        return file_hours[name], True
    return _carry_hours(name, {**file_hours, **session_hours})


def detect_event_id(api_url):
    """ID of the currently active conquest event, or None."""
    try:
        r = requests.get(f"{api_url.rstrip('/')}/v2/events/active", timeout=10)
        r.raise_for_status()
        ev = r.json()
        if ev.get("type") == "conquest":
            return ev["id"]
    except Exception:
        pass
    return None


def sync_live(api_url, event_id):
    """Rebuild regions/teams/completions from the live backend. Returns a summary dict."""
    api = api_url.rstrip("/")

    def get_json(path, **params):
        r = requests.get(f"{api}{path}", params=params or None, timeout=20)
        r.raise_for_status()
        return r.json()["data"]

    regions_raw = get_json(f"/v2/events/{event_id}/regions")
    terr_raw = get_json(f"/v2/events/{event_id}/territories")
    teams_raw = sorted(get_json("/v2/teams", event_id=event_id, per_page=50),
                       key=lambda t: t["name"])[:N_TEAMS]
    team_ids = [t["id"] for t in teams_raw]

    def fetch_progress(t):
        try:
            return t["id"], get_json(f"/v2/territories/{t['id']}/progress")
        except Exception:
            return t["id"], []

    with ThreadPoolExecutor(max_workers=8) as ex:
        progress = dict(ex.map(fetch_progress, terr_raw))

    by_region = {}
    for t in terr_raw:
        by_region.setdefault(t["region_id"], []).append(t)

    session_hours = {t["name"]: SS.hours.get(tid, t["hrs"])
                     for tid, _, _, t in build_tasks(SS.regions)}
    file_hours = _load_hours_file()

    team_index = {tid_: i for i, tid_ in enumerate(team_ids)}
    new_regions, counts = [], {}
    base_owners, base_region_owners, no_hours = {}, [], []
    for r in sorted(regions_raw, key=lambda r: r["name"]):
        terrs = sorted(by_region.get(r["id"], []),
                       key=lambda t: t.get("display_order") or 0)
        if not terrs:
            continue
        tasks = []
        for t in terrs:
            rows = progress.get(t["id"]) or []
            by_team = {row["team_id"]: row for row in rows}
            hrs, matched = _resolve_hours(t["name"], session_hours, file_hours)
            if not matched:
                no_hours.append(t["name"])
            tid = task_id(len(new_regions), len(tasks))
            counts[tid] = (
                [int(by_team[tid_]["completions"]) if tid_ in by_team else 0
                 for tid_ in team_ids] + [0] * N_TEAMS)[:N_TEAMS]
            base_owners[tid] = team_index.get(t.get("controlling_team_id"))
            tasks.append({
                "name": t["name"],
                "qty": int(rows[0]["required"]) if rows else 1,
                "pts": int(t.get("points") or 3),
                "hrs": hrs,
                "unv": not matched,
            })
        base_region_owners.append(team_index.get(r.get("controlling_team_id")))
        new_regions.append({
            "name": r["name"],
            "raid": any(w in r["name"].lower() for w in RAID_REGION_WORDS),
            "pts": int(r.get("points") or 20),
            "tasks": tasks,
        })

    SS.regions = new_regions
    SS.counts = counts
    SS.base_owners = base_owners
    SS.base_region_owners = base_region_owners
    SS.base_counts = {tid: list(v) for tid, v in counts.items()}
    SS.hours = {tid: t["hrs"] for tid, _, _, t in build_tasks(new_regions)}
    SS.team_names = ([t["name"] for t in teams_raw]
                     + [f"Team {i+1}" for i in range(N_TEAMS)])[:N_TEAMS]
    for i, name in enumerate(SS.team_names):
        SS[f"tn_{i}"] = name  # widget state would otherwise win over the new names
    SS.team_colors = [(teams_raw[i].get("color") if i < len(teams_raw) else None)
                      or TEAM_FALLBACK_COLORS[i] for i in range(N_TEAMS)]
    SS.epoch += 1
    return {
        "when": datetime.now().strftime("%H:%M:%S"),
        "regions": len(new_regions),
        "territories": sum(len(r["tasks"]) for r in new_regions),
        "teams": [t["name"] for t in teams_raw],
        "no_hours": no_hours,
    }


# One sync per browser session: everyone who opens (or F5s) the app starts on
# live data; failures fall back to the embedded draft with a warning.
if not SS.did_startup_sync:
    SS.did_startup_sync = True
    api = SS.get("live_api", DEFAULT_API_URL)
    eid = detect_event_id(api) or SS.get("live_event", DEFAULT_EVENT_ID)
    try:
        SS.live_summary = sync_live(api, eid)
        SS.live_error = None
        SS["live_event"] = eid  # show the event we actually synced in the sidebar
    except Exception as e:
        SS.live_error = f"{e}"

REGIONS = SS.regions
ALL_TASKS = build_tasks(REGIONS)


# ---------------------------------------------------------------------------
# Sidebar: scenario I/O, teams, point values
# ---------------------------------------------------------------------------

CONFIG_KEYS = {
    "pts_sweep": 0,
    "pts_super_1": 20,
    "pts_super_2": 12,
    "pts_super_3": 6,
}

with st.sidebar:
    st.title("⚔️ Conquest Planner")

    with st.expander("🛰️ Live data", expanded=SS.live_summary is None):
        api_url = st.text_input("API URL", DEFAULT_API_URL, key="live_api")
        event_id = st.text_input("Event ID", DEFAULT_EVENT_ID, key="live_event")
        st.caption("Sync replaces the board (regions, tasks, team names, completions) "
                   "with live event data. Hour estimates carry over by task name.")
        if st.button("🔄 Sync from live", width="stretch"):
            try:
                with st.spinner("Fetching live event data…"):
                    SS.live_summary = sync_live(api_url, event_id.strip())
                SS.live_error = None
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")
        if SS.live_summary:
            s = SS.live_summary
            st.success(f"Synced {s['when']} — {s['regions']} regions, "
                       f"{s['territories']} territories, teams: {', '.join(s['teams'])}")
            if s["no_hours"]:
                st.warning("No hour estimate matched for: " + ", ".join(s["no_hours"])
                           + f" — defaulted to {DEFAULT_HRS}h, fix in Task Hours tab.")

    up = st.file_uploader("Load scenario (.json)", type="json")
    if up is not None and up.file_id != SS.loaded_file:
        SS.loaded_file = up.file_id
        load_scenario(json.load(up))
        st.rerun()

    st.subheader("Teams")
    names = []
    for i in range(N_TEAMS):
        names.append(st.text_input(f"Team {i + 1}", SS.team_names[i], key=f"tn_{i}"))
    SS.team_names = names
    my_team = st.selectbox("Our team (for priorities)", range(N_TEAMS),
                           format_func=lambda i: names[i])

    with st.expander("Point values"):
        st.caption("Territory and region point values come from the event data "
                   "(each territory/region has its own worth).")
        cfg = {}
        labels = {
            "pts_sweep": "Region sweep / green-log bonus (TBD)",
            "pts_super_1": "Superlative 1st",
            "pts_super_2": "Superlative 2nd",
            "pts_super_3": "Superlative 3rd",
        }
        for k, default in CONFIG_KEYS.items():
            cfg[k] = st.number_input(labels[k], min_value=0, value=SS.get(k, default), key=k)

    st.download_button("💾 Save scenario", scenario_json(), "conquest_scenario.json",
                       "application/json", width="stretch")
    if st.button("🗑️ Reset all completions", width="stretch"):
        SS.counts = {tid: [0] * N_TEAMS for tid, *_ in ALL_TASKS}
        SS.base_owners = {}
        SS.base_region_owners = []
        SS.base_counts = {}
        SS.epoch += 1
        st.rerun()

# Sync superlative picks from their widget keys BEFORE scoring, so the
# scoreboard doesn't lag one rerun behind a selection.
for si, s in enumerate(SUPERLATIVES):
    for p in PLACES:
        k = f"sup_{si}_{p}"
        if k in SS and SS[k] in ["—"] + SS.team_names:
            SS.supers[s][p] = SS[k]

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def strict_max(vals):
    """Index of the strict maximum (>0), else None (tie or all zero)."""
    mx = max(vals)
    if mx > 0 and vals.count(mx) == 1:
        return vals.index(mx)
    return None


def held_owner(vals, incumbent):
    """Backend capture rule: the incumbent holds until a challenger STRICTLY
    exceeds them (ties don't unseat); with no incumbent, strict leader takes it."""
    if incumbent is None or not 0 <= incumbent < N_TEAMS:
        return strict_max(vals)
    best_v, best_i = max((v, i) for i, v in enumerate(vals) if i != incumbent)
    return best_i if best_v > vals[incumbent] else incumbent


def task_pts(t):
    return t.get("pts", 3)


def region_pts_value(region):
    return region.get("pts", 30 if region["raid"] else 20)


def compute_state(counts):
    """Territory owners, per-region territory tallies, region owners.

    Unedited counts return the live owner verbatim (the live data can hold
    states the capture rule alone can't reproduce, e.g. after admin remaps);
    the capture rule applies once a what-if edit diverges from the sync."""
    owners = {}
    for tid, *_ in ALL_TASKS:
        if counts[tid] == SS.base_counts.get(tid):
            owners[tid] = SS.base_owners.get(tid)
        else:
            owners[tid] = held_owner(counts[tid], SS.base_owners.get(tid))
    region_tallies, region_owners = [], []
    for ri, region in enumerate(REGIONS):
        tally = [0] * N_TEAMS
        untouched = True
        for ti in range(len(region["tasks"])):
            tid = task_id(ri, ti)
            untouched = untouched and owners[tid] == SS.base_owners.get(tid)
            o = owners[tid]
            if o is not None:
                tally[o] += 1
        base = SS.base_region_owners[ri] if ri < len(SS.base_region_owners) else None
        region_tallies.append(tally)
        region_owners.append(base if untouched and SS.base_counts else held_owner(tally, base))
    return owners, region_tallies, region_owners


def compute_scores(counts):
    owners, tallies, r_owners = compute_state(counts)
    terr = [0] * N_TEAMS
    terr_pts = [0] * N_TEAMS
    for tid, ri, region, t in ALL_TASKS:
        o = owners[tid]
        if o is not None:
            terr[o] += 1
            terr_pts[o] += task_pts(t)
    region_pts = [0] * N_TEAMS
    sweep_pts = [0] * N_TEAMS
    for ri, region in enumerate(REGIONS):
        o = r_owners[ri]
        if o is not None:
            region_pts[o] += region_pts_value(region)
        s = strict_max(tallies[ri]) if max(tallies[ri]) == len(region["tasks"]) else None
        if s is not None:
            sweep_pts[s] += cfg["pts_sweep"]
    super_pts = [0] * N_TEAMS
    place_val = {"1st": cfg["pts_super_1"], "2nd": cfg["pts_super_2"], "3rd": cfg["pts_super_3"]}
    for s in SUPERLATIVES:
        for p in PLACES:
            who = SS.supers[s].get(p, "—")
            if who in SS.team_names:
                super_pts[SS.team_names.index(who)] += place_val[p]
    total = [terr_pts[i] + region_pts[i] + sweep_pts[i] + super_pts[i]
             for i in range(N_TEAMS)]
    return {"territories": terr, "territory_pts": terr_pts, "region_pts": region_pts,
            "sweep_pts": sweep_pts, "super_pts": super_pts, "total": total,
            "owners": owners, "tallies": tallies, "region_owners": r_owners}


def team_points(counts, team):
    """Territory+region+sweep points for one team (superlatives excluded)."""
    s = compute_scores(counts)
    return s["total"][team] - s["super_pts"][team]


scores = compute_scores(SS.counts)


def owner_label(o):
    return SS.team_names[o] if o is not None else "— contested —"


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

if SS.live_error:
    st.warning(f"⚠️ Couldn't reach the live API ({SS.live_error}) — showing the "
               "offline draft task list. Use 🛰️ Live data in the sidebar to retry.")

tab_map, tab_board, tab_score, tab_prio, tab_hours = st.tabs(
    ["🗺️ Map", "📋 Board", "🏆 Scoreboard", "🎯 Priorities", "⏱️ Task Hours"])

# ---------------------------------------------------------------------------
# Map tab — clickable schematic war map
# ---------------------------------------------------------------------------

# Rough OSRS geography: (col, row) cells, row 0 = south. Regions are matched
# by keyword so live/draft naming differences don't matter.
_MAP_CELLS = [
    ("fremennik", (1, 2)), ("misthalin", (2, 2)), ("vampyr", (3, 2)),
    ("tirannwn", (0, 1)), ("kandarin", (1, 1)), ("karamja", (1, 1)),
    ("asgarnia", (2, 1)), ("morytania", (3, 1)),
    ("kourend", (0, 0)), ("varlamore", (1, 0)), ("desert", (2, 0)),
]
_SPARE_CELLS = [(3, 0), (0, 2), (4, 1), (4, 0), (4, 2)]


def _map_layout():
    """{region index: (x origin, y origin)} on the map canvas."""
    used, spare = set(), list(_SPARE_CELLS)
    cells = {}
    for ri, region in enumerate(REGIONS):
        name = region["name"].lower()
        cell = next((c for kw, c in _MAP_CELLS if kw in name and c not in used), None)
        if cell is None:
            cell = spare.pop(0)
        used.add(cell)
        cells[ri] = (cell[0] * 7.0, cell[1] * 3.2)
    return cells


def paint_tile(tid, choice):
    """Apply a map click: revert to live, or give a team the tile (capture rule)."""
    if choice == "live":
        SS.counts[tid] = list(SS.base_counts.get(tid, [0] * N_TEAMS))
    elif scores["owners"][tid] != choice:
        SS.counts[tid] = list(SS.counts[tid])
        SS.counts[tid][choice] = max(SS.counts[tid]) + 1


with tab_map:
    import plotly.graph_objects as go

    top = st.columns([3, 2])
    with top[0]:
        paint = st.radio(
            "Clicking a tile assigns it to:", list(range(N_TEAMS)) + ["live"],
            format_func=lambda o: "↩️ Revert to live" if o == "live" else SS.team_names[o],
            horizontal=True, key="map_paint")
    with top[1]:
        legend = "  ".join(
            f"<span style='color:{SS.team_colors[i]}'>⬤</span> {SS.team_names[i]}"
            for i in range(N_TEAMS)) + f"  <span style='color:{NEUTRAL_COLOR}'>⬤</span> contested"
        st.markdown(legend, unsafe_allow_html=True)
        st.caption("Tile = territory (click to flip) · box border = region controller")

    layout_xy = _map_layout()
    xs, ys, colors, texts, hovers, tids = [], [], [], [], [], []
    fig = go.Figure()
    for ri, region in enumerate(REGIONS):
        ox, oy = layout_xy[ri]
        n = len(region["tasks"])
        r_owner = scores["region_owners"][ri]
        r_color = SS.team_colors[r_owner] if r_owner is not None else NEUTRAL_COLOR
        fig.add_shape(type="rect", x0=ox - 0.7, x1=ox + (n - 1) * 1.2 + 0.7,
                      y0=oy - 0.75, y1=oy + 0.75,
                      line={"color": r_color, "width": 3}, opacity=0.9)
        star = " ⭐" if region["raid"] else ""
        holder = SS.team_names[r_owner] if r_owner is not None else "contested"
        fig.add_annotation(x=ox + (n - 1) * 0.6, y=oy + 1.15,
                           text=f"<b>{region['name']}{star}</b> · {region_pts_value(region)}p · {holder}",
                           showarrow=False, font={"size": 11, "color": r_color})
        for ti, t in enumerate(region["tasks"]):
            tid = task_id(ri, ti)
            o = scores["owners"][tid]
            xs.append(ox + ti * 1.2)
            ys.append(oy)
            colors.append(SS.team_colors[o] if o is not None else NEUTRAL_COLOR)
            texts.append(str(task_pts(t)) if task_pts(t) != 3 else "")
            counts_str = " · ".join(f"{SS.team_names[i]}: {SS.counts[tid][i]}"
                                    for i in range(N_TEAMS))
            hovers.append(f"<b>{t['name']}</b> (x{t['qty']}, {task_pts(t)}pts)<br>"
                          f"owner: {owner_label(o)}<br>{counts_str}")
            tids.append(tid)
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=texts, customdata=tids,
        marker={"symbol": "square", "size": 34, "color": colors,
                "line": {"color": "rgba(255,255,255,0.55)", "width": 1}},
        textfont={"color": "white", "size": 11},
        hovertext=hovers, hoverinfo="text"))
    fig.update_layout(
        height=560, margin={"l": 10, "r": 10, "t": 10, "b": 10},
        showlegend=False, dragmode=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True, "scaleanchor": "x", "scaleratio": 1.35},
    )

    event = st.plotly_chart(fig, on_select="rerun", selection_mode=("points",),
                            key=f"map_{SS.epoch}", config={"displayModeBar": False})
    points = event.get("selection", {}).get("points", []) if event else []
    if points:
        paint_tile(points[0]["customdata"], SS.map_paint)
        SS.epoch += 1  # remount editors + clear the map selection
        st.rerun()

    mcols = st.columns(N_TEAMS)
    order = sorted(range(N_TEAMS), key=lambda i: -scores["total"][i])
    for rank, i in enumerate(order):
        with mcols[rank]:
            st.metric(f"#{rank + 1}  {SS.team_names[i]}", f"{scores['total'][i]} pts",
                      f"{scores['territories'][i]} territories")

with tab_board:
    st.caption("Enter cumulative **completions** (batches) per team per task. "
               "The current holder keeps a territory until a challenger **strictly exceeds** "
               "them (live rule — ties don't flip). ⚠️ = quantity/rate unverified.")
    left, right = st.columns(2)
    for ri, region in enumerate(REGIONS):
        star = " ⭐" if region["raid"] else ""
        r_owner = scores["region_owners"][ri]
        with (left if ri % 2 == 0 else right):
            st.markdown(f"**{ri + 1}. {region['name']}{star}** — region: "
                        f"{'🏳️ ' + owner_label(None) if r_owner is None else '🚩 ' + SS.team_names[r_owner]}")
            rows = []
            for ti, t in enumerate(region["tasks"]):
                tid = task_id(ri, ti)
                warn = " ⚠️" if t["unv"] else ""
                pts = f" · {task_pts(t)}pts" if task_pts(t) != 3 else ""
                row = {"Task": f"{t['name']}{warn}  (x{t['qty']}){pts}"}
                for i in range(N_TEAMS):
                    row[SS.team_names[i]] = SS.counts[tid][i]
                row["Owner"] = owner_label(scores["owners"][tid])
                rows.append(row)
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df, key=f"ed_{ri}_{SS.epoch}", hide_index=True, width="stretch",
                disabled=["Task", "Owner"],
                column_config={SS.team_names[i]: st.column_config.NumberColumn(
                    min_value=0, step=1, width="small") for i in range(N_TEAMS)},
            )
            changed = False
            for ti in range(len(region["tasks"])):
                tid = task_id(ri, ti)
                new = [int(edited.iloc[ti][SS.team_names[i]] or 0) for i in range(N_TEAMS)]
                if new != SS.counts[tid]:
                    SS.counts[tid] = new
                    changed = True
            if changed:
                st.rerun()

with tab_score:
    cols = st.columns(N_TEAMS)
    order = sorted(range(N_TEAMS), key=lambda i: -scores["total"][i])
    for rank, i in enumerate(order):
        with cols[rank]:
            st.metric(f"#{rank + 1}  {SS.team_names[i]}", f"{scores['total'][i]} pts",
                      f"{scores['territories'][i]} territories")
    st.divider()

    breakdown = pd.DataFrame({
        "Team": SS.team_names,
        "Territories": scores["territories"],
        "Territory pts": scores["territory_pts"],
        "Region pts": scores["region_pts"],
        "Sweep pts": scores["sweep_pts"],
        "Superlative pts": scores["super_pts"],
        "Total": scores["total"],
    }).sort_values("Total", ascending=False)
    st.dataframe(breakdown, hide_index=True, width="stretch")

    st.subheader("Region control")
    region_rows = []
    for ri, region in enumerate(REGIONS):
        row = {"Region": f"{region['name']}{' ⭐' if region['raid'] else ''}",
               "Worth": region_pts_value(region),
               "Leader": owner_label(scores["region_owners"][ri])}
        for i in range(N_TEAMS):
            row[SS.team_names[i]] = scores["tallies"][ri][i]
        region_rows.append(row)
    st.dataframe(pd.DataFrame(region_rows), hide_index=True, width="stretch")

    st.subheader("Superlatives (manual)")
    st.caption("Set placements as they stand — tracked outside the completion counts.")
    scols = st.columns(len(SUPERLATIVES))
    for si, s in enumerate(SUPERLATIVES):
        with scols[si]:
            st.markdown(f"**{s}**")
            for p in PLACES:
                k = f"sup_{si}_{p}"
                options = ["—"] + SS.team_names
                if SS.get(k) not in options:
                    SS[k] = SS.supers[s].get(p) if SS.supers[s].get(p) in options else "—"
                SS.supers[s][p] = st.selectbox(p, options, key=k)

with tab_prio:
    st.caption(f"Marginal value for **{SS.team_names[my_team]}**: cheapest points per hour "
               "first, using current margins. 'Take cost' = completions needed to own the "
               "territory outright; point swing includes any region flip or sweep it causes.")

    offense, defense = [], []
    for tid, ri, region, t in ALL_TASKS:
        counts = SS.counts[tid]
        mine = counts[my_team]
        best_other = max(c for i, c in enumerate(counts) if i != my_team)
        hrs = SS.hours[tid]
        if scores["owners"][tid] == my_team:
            margin = mine - best_other
            # points at stake if the nearest rival takes this territory
            rival = max((c, i) for i, c in enumerate(counts) if i != my_team)[1]
            sim = {k: list(v) for k, v in SS.counts.items()}
            sim[tid][rival] = mine + 1
            at_stake = team_points(SS.counts, my_team) - team_points(sim, my_team)
            defense.append({
                "Region": region["name"], "Task": t["name"], "Margin": margin,
                "Rival hrs to flip": round((margin + 1) * hrs, 1),
                "Pts we'd lose": at_stake,
                "Status": "🔥 AT RISK" if margin <= 1 else "🛡️ safe-ish",
            })
        else:
            need = best_other + 1 - mine
            take_hrs = need * hrs
            sim = {k: list(v) for k, v in SS.counts.items()}
            sim[tid][my_team] = best_other + 1
            gain = team_points(sim, my_team) - team_points(SS.counts, my_team)
            sim_scores = compute_scores(sim)
            note = []
            if sim_scores["region_owners"][ri] == my_team != scores["region_owners"][ri]:
                note.append("takes region 🚩")
            cur_owner = scores["owners"][tid]
            if cur_owner is not None and scores["region_owners"][ri] == cur_owner \
                    and sim_scores["region_owners"][ri] != cur_owner:
                note.append(f"strips {SS.team_names[cur_owner]}'s region")
            offense.append({
                "Region": region["name"], "Task": t["name"] + (" ⚠️" if t["unv"] else ""),
                "Held by": owner_label(cur_owner),
                "Take cost": need, "Est hrs": round(take_hrs, 1),
                "Pts gained": gain,
                "Pts/hr": round(gain / take_hrs, 2) if take_hrs else 0.0,
                "Effect": ", ".join(note),
            })

    st.subheader("⚔️ Offense — best value flips")
    off_df = pd.DataFrame(offense).sort_values(["Pts/hr", "Pts gained"], ascending=False)
    st.dataframe(off_df, hide_index=True, width="stretch",
                 column_config={"Pts/hr": st.column_config.NumberColumn(format="%.2f")})

    st.subheader("🛡️ Defense — territories we hold")
    if defense:
        st.dataframe(pd.DataFrame(defense).sort_values("Margin"),
                     hide_index=True, width="stretch")
    else:
        st.info("We don't own any territories yet in this scenario.")

with tab_hours:
    st.caption("Estimated solo hours **per completion** — drives the Pts/hr ranking. "
               "⚠️ rows are unverified draft numbers; edit freely (saved with the scenario).")
    hr_rows = [{"Region": REGIONS[ri]["name"],
                "Task": t["name"] + (" ⚠️" if t["unv"] else ""),
                "Qty/completion": t["qty"],
                "Hrs/completion": SS.hours[tid]}
               for tid, ri, _, t in ALL_TASKS]
    hr_edit = st.data_editor(
        pd.DataFrame(hr_rows), key=f"hrs_{SS.epoch}", hide_index=True, width="stretch",
        disabled=["Region", "Task", "Qty/completion"],
        column_config={"Hrs/completion": st.column_config.NumberColumn(
            min_value=0.1, step=0.1, format="%.1f")})
    for idx, (tid, *_rest) in enumerate(ALL_TASKS):
        SS.hours[tid] = float(hr_edit.iloc[idx]["Hrs/completion"])

    st.download_button(
        "⬇️ Download hours.json",
        json.dumps({t["name"]: SS.hours[tid] for tid, _, _, t in ALL_TASKS}, indent=1),
        "hours.json", "application/json",
        help="Commit this next to app.py — startup sync uses it as the hour source, "
             "so everyone opening the hosted app gets these estimates.")
