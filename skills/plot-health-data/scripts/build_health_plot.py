#!/usr/bin/env python3
"""Build a health-plot HTML fragment from Food Log JSONL and Garmin archives."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

TARGETS = {"calories": 2077.0, "protein_g": 150.0, "carbs_g": 194.0, "fat_g": 86.0}


def num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_food(path: Path) -> tuple[str, dict[str, Any]]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError(f"{path}: empty Food Log")
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{path}: JSONL lines must be objects")
        entry_id, revision = str(record.get("entry_id", "")), record.get("revision")
        if not entry_id or not isinstance(revision, int):
            raise ValueError(f"{path}: invalid entry_id or revision")
        if entry_id not in latest or revision > latest[entry_id]["revision"]:
            latest[entry_id] = record
    active = [r for r in latest.values() if r.get("status") != "Deleted"]
    local_date = str((active[0] if active else records[0]).get("local_date") or "")
    if not local_date:
        raise ValueError(f"{path}: missing local_date")
    totals = {key: 0.0 for key in TARGETS}
    incomplete: list[str] = []
    for record in active:
        known = record.get("known_nutrition_subtotal") or {}
        for key in totals:
            totals[key] += num(known.get(key)) or 0.0
        incomplete.extend(str(x) for x in record.get("nutrition_incomplete_for") or [])
    return local_date, {
        "food_present": True,
        "food_incomplete": bool(incomplete),
        "incomplete_foods": sorted(set(incomplete)),
        "food_calories": round(totals["calories"], 2),
        "protein_g": round(totals["protein_g"], 2),
        "carbs_g": round(totals["carbs_g"], 2),
        "fat_g": round(totals["fat_g"], 2),
        "meal_count": len(active),
    }


def activity(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get("activityType")
    if isinstance(kind, dict):
        kind = kind.get("typeKey")
    seconds = num(item.get("duration"))
    return {
        "name": str(item.get("activityName") or kind or "Activity"),
        "type": str(kind or "activity"),
        "calories": num(item.get("calories")),
        "minutes": round(seconds / 60.0, 1) if seconds is not None else None,
        "steps": num(item.get("steps")),
    }


def read_garmin(path: Path) -> tuple[str, dict[str, Any]]:
    record = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(record, dict):
        raise ValueError(f"{path}: expected a JSON object")
    local_date, stats = str(record.get("date") or ""), record.get("stats")
    if not local_date or not isinstance(stats, dict) or stats.get("error") or not stats:
        raise ValueError(f"{path}: missing valid date/stats or suspected truncation")
    end_local = str(stats.get("wellnessEndTimeLocal") or "")
    partial = end_local.startswith(local_date)
    raw_activities = record.get("activities")
    activities = (
        [activity(x) for x in raw_activities if isinstance(x, dict)]
        if isinstance(raw_activities, list)
        else []
    )
    sleep = record.get("sleep")
    sleep_day = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
    sleep_seconds = num(sleep_day.get("sleepTimeSeconds")) if isinstance(sleep_day, dict) else None
    scores = sleep_day.get("sleepScores") if isinstance(sleep_day, dict) else None
    overall = scores.get("overall") if isinstance(scores, dict) else None
    return local_date, {
        "garmin_present": True,
        "garmin_partial": partial,
        "data_through_local": end_local or None,
        "total_burn": num(stats.get("totalKilocalories")),
        "active_burn": num(stats.get("activeKilocalories")),
        "bmr_burn": num(stats.get("bmrKilocalories")),
        "steps": num(stats.get("totalSteps")),
        "step_goal": num(stats.get("dailyStepGoal")),
        "resting_hr": num(stats.get("restingHeartRate")),
        "sleep_hours": round(sleep_seconds / 3600.0, 2) if sleep_seconds is not None else None,
        "sleep_score": num(overall.get("value")) if isinstance(overall, dict) else None,
        "activities": activities,
    }


def build_rows(
    foods: list[Path],
    garmins: list[Path],
    start: date | None,
    end: date | None,
) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for path in foods:
        day, values = read_food(path)
        by_day.setdefault(day, {}).update(values)
    for path in garmins:
        day, values = read_garmin(path)
        by_day.setdefault(day, {}).update(values)
    if not by_day and (start is None or end is None):
        raise ValueError("provide data or both --start and --end")
    known_dates = [date.fromisoformat(x) for x in by_day]
    start = start or min(known_dates)
    end = end or max(known_dates)
    if end < start:
        raise ValueError("end date precedes start date")
    rows = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        row: dict[str, Any] = {
            "date": day.isoformat(),
            "day": day.strftime("%a"),
            "label": day.strftime("%b %-d"),
            "food_present": False,
            "food_incomplete": False,
            "garmin_present": False,
            "garmin_partial": False,
            "activities": [],
        }
        row.update(by_day.get(day.isoformat(), {}))
        rows.append(row)
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    targets = json.dumps(TARGETS, separators=(",", ":"))
    template = """<div id="health-plot-v1">
  <div class="viz-row hp-legend">
    <span><i class="hp-swatch hp-food"></i>Food</span>
    <span><i class="hp-swatch hp-rest"></i>Resting burn</span>
    <span><i class="hp-swatch hp-active"></i>Active burn</span>
    <span><i class="hp-swatch hp-partial"></i>Partial / lower bound</span>
  </div>
  <section class="hp-section"><h3>Energy intake and expenditure</h3>
    <p class="text-muted text-small">Food versus Garmin total burn; active burn is included in total burn.</p>
    <svg id="hp-energy" class="hp-chart" role="img" aria-label="Daily food and energy expenditure"></svg>
  </section>
  <section class="hp-section"><h3>Movement and exercise</h3>
    <p class="text-muted text-small">Steps with recorded exercise events; workout calories are annotations, not added twice.</p>
    <svg id="hp-activity" class="hp-chart" role="img" aria-label="Daily steps and exercise events"></svg>
  </section>
  <section class="hp-section"><h3>Nutrition target coverage</h3>
    <p class="text-muted text-small">Protein, carbohydrate, and fat as percentages of daily targets.</p>
    <svg id="hp-macros" class="hp-chart" role="img" aria-label="Daily macro target coverage"></svg>
  </section>
  <div class="hp-split">
    <section class="hp-section"><h3>Sleep</h3><svg id="hp-sleep" class="hp-mini" role="img" aria-label="Daily sleep hours"></svg></section>
    <section class="hp-section"><h3>Resting heart rate</h3><svg id="hp-rhr" class="hp-mini" role="img" aria-label="Daily resting heart rate"></svg></section>
  </div>
  <p class="text-muted text-small hp-note">Missing days are gaps, never zero. ≥ marks incomplete food nutrition. ◐ marks a partial Garmin day.</p>
</div>
<style>
#health-plot-v1 {{ width:100%;color:var(--foreground) }}
#health-plot-v1 .hp-legend {{ gap:12px;margin-bottom:16px;color:var(--muted-foreground) }}
#health-plot-v1 .hp-legend span {{ display:inline-flex;align-items:center;gap:5px }}
#health-plot-v1 .hp-swatch {{ width:11px;height:11px;display:inline-block }}
#health-plot-v1 .hp-food {{ background:var(--viz-series-1) }}
#health-plot-v1 .hp-rest {{ background:var(--muted);border:1px solid var(--muted-foreground) }}
#health-plot-v1 .hp-active {{ background:var(--viz-series-2) }}
#health-plot-v1 .hp-partial {{ border:2px dashed var(--muted-foreground) }}
#health-plot-v1 .hp-section {{ margin-bottom:20px }}
#health-plot-v1 .hp-section h3 {{ margin-bottom:2px }}
#health-plot-v1 .hp-section p {{ margin:0 0 6px }}
#health-plot-v1 .hp-chart,#health-plot-v1 .hp-mini {{ width:100%;display:block;overflow:visible }}
#health-plot-v1 .hp-split {{ display:grid;grid-template-columns:1fr 1fr;gap:18px }}
#health-plot-v1 .grid {{ stroke:var(--border);stroke-width:1 }}
#health-plot-v1 .target {{ stroke:var(--foreground);stroke-width:1.5;stroke-dasharray:5 4 }}
#health-plot-v1 .label {{ fill:var(--muted-foreground);font-size:11px }}
#health-plot-v1 .value {{ fill:var(--foreground);font-size:11px;font-weight:500 }}
#health-plot-v1 .food {{ fill:var(--viz-series-1) }}
#health-plot-v1 .rest {{ fill:var(--muted);stroke:var(--muted-foreground) }}
#health-plot-v1 .active {{ fill:var(--viz-series-2) }}
#health-plot-v1 .steps {{ fill:var(--viz-series-3) }}
#health-plot-v1 .protein {{ fill:var(--viz-series-1) }}
#health-plot-v1 .carbs {{ fill:var(--viz-series-2) }}
#health-plot-v1 .fat {{ fill:var(--viz-series-3) }}
#health-plot-v1 .partial {{ stroke:var(--foreground);stroke-width:1.5;stroke-dasharray:4 3 }}
#health-plot-v1 .missing {{ fill:none;stroke:var(--border);stroke-dasharray:3 3 }}
#health-plot-v1 .trend {{ fill:none;stroke:var(--viz-series-1);stroke-width:2 }}
#health-plot-v1 .point {{ fill:var(--background);stroke:var(--viz-series-1);stroke-width:2 }}
#health-plot-v1 .event {{ fill:var(--viz-series-2);stroke:var(--background) }}
#health-plot-v1 .hp-note {{ margin-top:-8px }}
@media(max-width:520px){{#health-plot-v1 .hp-split{{grid-template-columns:1fr}}}}
</style>
<script>
(function(){{
"use strict";
const root=document.getElementById("health-plot-v1"),rows=__PAYLOAD__,targets=__TARGETS__,ns="http://www.w3.org/2000/svg";
function add(svg,tag,a,text,title){{const e=document.createElementNS(ns,tag);Object.keys(a||{{}}).forEach(k=>e.setAttribute(k,a[k]));if(text!==undefined)e.textContent=text;if(title){{const t=document.createElementNS(ns,"title");t.textContent=title;e.appendChild(t)}}svg.appendChild(e);return e}}
function setup(id,h,left=48){{const s=document.getElementById(id),w=Math.max(320,Math.round(s.getBoundingClientRect().width||root.getBoundingClientRect().width));s.setAttribute("viewBox",`0 0 ${w} ${h}`);s.setAttribute("height",h);s.replaceChildren();const m={{top:25,right:12,bottom:48,left}};return{{s,w,h,m,pw:w-m.left-m.right,ph:h-m.top-m.bottom}}}}
function axes(c,max,ticks,suffix=""){{ticks.forEach(v=>{{const y=c.m.top+c.ph-v/max*c.ph;add(c.s,"line",{{x1:c.m.left,x2:c.w-c.m.right,y1:y,y2:y,class:"grid"}});add(c.s,"text",{{x:c.m.left-7,y:y+4,"text-anchor":"end",class:"label"}},v.toLocaleString()+suffix)}})}}
function labels(c){{const slot=c.pw/rows.length;rows.forEach((d,i)=>{{const x=c.m.left+slot*(i+.5);add(c.s,"text",{{x,y:c.m.top+c.ph+18,"text-anchor":"middle",class:"value"}},d.day);add(c.s,"text",{{x,y:c.m.top+c.ph+34,"text-anchor":"middle",class:"label"}},d.label)}})}}
function missing(c,x,w){{add(c.s,"rect",{{x:x-w/2,y:c.m.top+c.ph-18,width:w,height:18,rx:2,class:"missing"}})}}
function energy(){{const c=setup("hp-energy",300),vals=rows.flatMap(d=>[d.food_calories,d.total_burn].filter(v=>v!=null)),max=Math.max(2500,Math.ceil(Math.max(...vals,2500)/500)*500);axes(c,max,Array.from({{length:max/500+1}},(_,i)=>i*500));const slot=c.pw/rows.length,gw=Math.min(72,slot*.76),bw=gw/2-3;rows.forEach((d,i)=>{{const x=c.m.left+slot*(i+.5);if(d.food_present){{const h=d.food_calories/max*c.ph,y=c.m.top+c.ph-h,p=d.food_incomplete?"≥":"";add(c.s,"rect",{{x:x-gw/2,y,width:bw,height:h,rx:2,class:"food"+(d.food_incomplete?" partial":"")}},undefined,`${d.day} ${d.label}: food ${p}${Math.round(d.food_calories)} kcal`)}}else missing(c,x-gw/4,bw);if(d.garmin_present&&d.total_burn!=null){{const active=d.active_burn||0,rest=d.bmr_burn??Math.max(0,d.total_burn-active),rh=rest/max*c.ph,ah=active/max*c.ph,rx=x+3,ry=c.m.top+c.ph-rh,ay=ry-ah,tip=`${d.day} ${d.label}: total burn ${Math.round(d.total_burn)} kcal; active ${Math.round(active)} kcal`;add(c.s,"rect",{{x:rx,y:ry,width:bw,height:rh,rx:1,class:"rest"}},undefined,tip);add(c.s,"rect",{{x:rx,y:ay,width:bw,height:ah,rx:1,class:"active"+(d.garmin_partial?" partial":"")}},undefined,tip)}}else missing(c,x+gw/4,bw)}});labels(c)}}
function activity(){{const c=setup("hp-activity",275),max=Math.max(12000,Math.ceil(Math.max(...rows.map(d=>d.steps||0),10000)/2000)*2000);axes(c,max,Array.from({{length:max/2000+1}},(_,i)=>i*2000));const slot=c.pw/rows.length,bw=Math.min(52,slot*.55);rows.forEach((d,i)=>{{const x=c.m.left+slot*(i+.5);if(d.garmin_present&&d.steps!=null){{const h=d.steps/max*c.ph,y=c.m.top+c.ph-h,p=d.garmin_partial?"≥":"";add(c.s,"rect",{{x:x-bw/2,y,width:bw,height:h,rx:2,class:"steps"+(d.garmin_partial?" partial":"")}},undefined,`${d.day} ${d.label}: ${p}${Math.round(d.steps)} steps`);(d.activities||[]).slice(0,3).forEach((a,j)=>{{const kcal=a.calories==null?"":`; ${Math.round(a.calories)} kcal`,mins=a.minutes==null?"":`; ${a.minutes} min`;add(c.s,"circle",{{cx:x,cy:Math.max(c.m.top+8,y-10-j*13),r:5,class:"event"}},undefined,a.name+kcal+mins)}})}}else missing(c,x,bw)}});const gy=c.m.top+c.ph-10000/max*c.ph;add(c.s,"line",{{x1:c.m.left,x2:c.w-c.m.right,y1:gy,y2:gy,class:"target"}});add(c.s,"text",{{x:c.w-c.m.right,y:gy-5,"text-anchor":"end",class:"value"}},"10k");labels(c)}}
function macros(){{const c=setup("hp-macros",285),max=150;axes(c,max,[0,25,50,75,100,125,150],"%");const slot=c.pw/rows.length,gw=Math.min(70,slot*.8),bw=gw/3-2,ms=[["protein_g","protein"],["carbs_g","carbs"],["fat_g","fat"]];rows.forEach((d,i)=>{{const x=c.m.left+slot*(i+.5);if(!d.food_present){{missing(c,x,gw);return}}ms.forEach((m,j)=>{{const pct=(d[m[0]]||0)/targets[m[0]]*100,h=Math.min(pct,max)/max*c.ph,bx=x-gw/2+j*(bw+3),y=c.m.top+c.ph-h,p=d.food_incomplete?"≥":"";add(c.s,"rect",{{x:bx,y,width:bw,height:h,rx:1,class:m[1]+(d.food_incomplete?" partial":"")}},undefined,`${d.day} ${d.label}: ${m[1]} ${p}${(d[m[0]]||0).toFixed(1)} g (${Math.round(pct)}%)`)}})}});const ty=c.m.top+c.ph-100/max*c.ph;add(c.s,"line",{{x1:c.m.left,x2:c.w-c.m.right,y1:ty,y2:ty,class:"target"}});labels(c)}}
function mini(id,field,max,ticks,suffix){{const c=setup(id,220,42);axes(c,max,ticks,suffix);const slot=c.pw/rows.length,pts=[];rows.forEach((d,i)=>{{if(d[field]!=null)pts.push([c.m.left+slot*(i+.5),c.m.top+c.ph-d[field]/max*c.ph,d])}});if(pts.length>1)add(c.s,"polyline",{{points:pts.map(p=>p[0]+","+p[1]).join(" "),class:"trend"}});pts.forEach(p=>add(c.s,"circle",{{cx:p[0],cy:p[1],r:4,class:"point"}},undefined,`${p[2].day} ${p[2].label}: ${p[2][field]} ${field==="sleep_hours"?"h":"bpm"}`));labels(c)}}
function draw(){{energy();activity();macros();mini("hp-sleep","sleep_hours",10,[0,2,4,6,8,10],"h");mini("hp-rhr","resting_hr",100,[0,25,50,75,100],"")}}
draw();let timer;window.addEventListener("resize",()=>{{clearTimeout(timer);timer=setTimeout(draw,120)}})
}})();
</script>
"""
    return (
        template.replace("{{", "{")
        .replace("}}", "}")
        .replace("__PAYLOAD__", payload)
        .replace("__TARGETS__", targets)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--food-log", action="append", default=[], type=Path)
    parser.add_argument("--garmin", action="append", default=[], type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        rows = build_rows(args.food_log, args.garmin, args.start, args.end)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(rows), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "days": len(rows)}, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
