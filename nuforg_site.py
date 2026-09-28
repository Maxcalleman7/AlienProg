"""Interactive HTML report from a NUFORC sightings CSV.

Usage: python nuforg_site.py ufo_sightings.csv

Writes nuforc_report.html and opens it in the browser.
"""

import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

import pandas as pd

from timezones import to_local

# Years used for the "typical day" calculations. Reporting exploded after the
# mid-1990s and 2023 is a partial year, so we only use full recent years.
START_YEAR = 1995
END_YEAR = 2022
TOP_N = 15
OUT_FILE = Path("nuforc_report.html")

TIME_COLS = ["reported_date_time", "datetime", "date_time", "Date / Time", "date", "occurred"]
SHAPE_COLS = ["shape", "Shape"]
STATE_COLS = ["state", "State"]
COUNTRY_COLS = ["country_code", "country", "Country"]


def first_col(df, names):
    return next((c for c in names if c in df.columns), None)


def label_for(md):
    d = datetime.strptime("2024-" + md, "%Y-%m-%d")
    return d.strftime("%b") + " " + str(d.day)


def build_data(path):
    df = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    tcol = first_col(df, TIME_COLS)
    if tcol is None:
        sys.exit(f"No time column found. Columns are: {list(df.columns)}")
    df["t"] = pd.to_datetime(df[tcol], errors="coerce")
    df = df.dropna(subset=["t"])
    stcol = first_col(df, STATE_COLS)
    ccol = first_col(df, COUNTRY_COLS)
    df["t"] = to_local(df.t, df[stcol] if stcol else None, df[ccol] if ccol else None)
    df = df[(df.t.dt.year >= 1940) & (df.t.dt.year <= pd.Timestamp.now().year)]
    df["year"] = df.t.dt.year
    df["md"] = df.t.dt.strftime("%m-%d")

    # Simple counts
    years_all = list(range(int(df.year.min()), int(df.year.max()) + 1))
    per_year = df.groupby("year").size().reindex(years_all, fill_value=0)
    month = df.groupby(df.t.dt.month).size().reindex(range(1, 13), fill_value=0)
    hour = None
    if (df.t.dt.hour != 0).any():
        hour = df.groupby(df.t.dt.hour).size().reindex(range(24), fill_value=0)

    scol = first_col(df, SHAPE_COLS)
    shapes = df[scol].astype(str).str.lower().value_counts().head(15) if scol else None
    states = df[stcol].astype(str).str.upper().value_counts().head(15) if stcol else None

    # Calendar-day analysis over full recent years
    all_md = pd.date_range("2024-01-01", "2024-12-31").strftime("%m-%d")
    years = list(range(START_YEAR, END_YEAR + 1))
    recent = df[(df.year >= START_YEAR) & (df.year <= END_YEAR)]
    grid = (recent.groupby(["md", "year"]).size().unstack(fill_value=0)
            .reindex(index=all_md, columns=years, fill_value=0))
    avg = grid.sum(axis=1) / len(years)
    typical = float(avg.median())

    top = []
    for md in avg.sort_values(ascending=False).head(TOP_N).index:
        row = grid.loc[md]
        total = int(row.sum())
        peak_year = int(row.idxmax())
        peak_count = int(row.max())
        peak_share = peak_count / total if total else 0
        years_above = int((row > 2 * typical).sum())
        frac_above = years_above / len(years)
        if frac_above >= 0.5:
            verdict = "Recurring"
        elif peak_share >= 0.2:
            verdict = "One-off spike"
        else:
            verdict = "Mixed"
        top.append({
            "md": md, "label": label_for(md), "avg": round(float(avg[md]), 1),
            "peakYear": peak_year, "peakCount": peak_count,
            "peakShare": round(peak_share * 100), "yearsAbove": years_above,
            "verdict": verdict,
        })

    def series(s):
        return {"labels": [str(i) for i in s.index], "values": [int(v) for v in s.values]}

    return {
        "summary": {
            "total": int(len(df)),
            "first": str(df.t.min().date()),
            "last": str(df.t.max().date()),
            "typical": round(typical, 1),
            "topDay": top[0]["label"] if top else "-",
            "topAvg": top[0]["avg"] if top else 0,
            "startYear": START_YEAR, "endYear": END_YEAR,
        },
        "perYear": series(per_year),
        "month": {"labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                  "values": [int(v) for v in month.values]},
        "hour": series(hour) if hour is not None else None,
        "shapes": series(shapes) if shapes is not None else None,
        "states": series(states) if states is not None else None,
        "daily": {"keys": list(all_md), "labels": [label_for(m) for m in all_md],
                  "values": [round(float(v), 2) for v in avg.values]},
        "days": {md: [int(v) for v in grid.loc[md].values] for md in all_md},
        "years": years,
        "typical": round(typical, 2),
        "top": top,
    }


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NUFORC Sightings Explorer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0b1020; --panel: #131a30; --line: #243055; --text: #e6ecff;
    --muted: #9aa8cc; --accent: #7cf5c4; --accent2: #8ea2ff; --warn: #ffb86b;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, "Segoe UI", sans-serif; background: var(--bg);
         color: var(--text); line-height: 1.5; }
  header { padding: 32px 24px 8px; max-width: 1100px; margin: 0 auto; }
  h1 { margin: 0; font-size: 28px; }
  h1 span { color: var(--accent); }
  header p { color: var(--muted); margin: 6px 0 0; }
  main { max-width: 1100px; margin: 0 auto; padding: 16px 24px 60px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
  .card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
  .card .k { color: var(--muted); font-size: 13px; }
  .card .v { font-size: 26px; font-weight: 650; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; margin-top: 16px; }
  .panel h2 { margin: 0 0 4px; font-size: 17px; }
  .panel .sub { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
  .chart { position: relative; height: 280px; }
  .wide { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; }
  tbody tr { cursor: pointer; }
  tbody tr:hover, tbody tr.sel { background: rgba(142,162,255,0.12); }
  .tag { padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid; white-space: nowrap; }
  .Recurring { color: var(--accent); border-color: var(--accent); }
  .One-off { color: var(--warn); border-color: var(--warn); }
  .Mixed { color: var(--muted); border-color: var(--muted); }
  select { background: var(--bg); color: var(--text); border: 1px solid var(--line);
           border-radius: 8px; padding: 6px 10px; font-size: 14px; }
  .note { color: var(--muted); font-size: 13px; margin-top: 10px; }
  .scroll { overflow-x: auto; }
  #nochart { display: none; background: #3a2230; border: 1px solid #a04a6a; padding: 12px;
             border-radius: 8px; margin: 12px 0; }
</style>
</head>
<body>
<header>
  <h1><span>&#128760;</span> NUFORC Sightings Explorer</h1>
  <p>Built from your local CSV. Click a row in the table, or pick any date, to see its year-by-year story.</p>
</header>
<main>
  <div id="nochart">The charts library did not load. Check your internet connection and refresh.</div>
  <div class="cards" id="cards"></div>

  <div class="grid">
    <section class="panel wide">
      <h2>Sightings per year</h2>
      <p class="sub">Look for the jump in the late 1990s. Internet reporting and media attention are the usual suspects.</p>
      <div class="chart"><canvas id="cYear"></canvas></div>
    </section>

    <section class="panel wide">
      <h2>Average sightings for every calendar day</h2>
      <p class="sub" id="dailySub"></p>
      <div class="chart"><canvas id="cDaily"></canvas></div>
    </section>

    <section class="panel wide">
      <h2>Top days: recurring habit or one-off event?</h2>
      <p class="sub" id="topSub"></p>
      <div class="scroll">
        <table>
          <thead><tr><th>Date</th><th>Avg / year</th><th>Peak year</th><th>Peak count</th>
            <th>Peak share</th><th>Years &gt; 2x typical</th><th>Verdict</th></tr></thead>
          <tbody id="topBody"></tbody>
        </table>
      </div>
      <p class="note"><b>Verdict rule:</b> Recurring = more than 2x the typical day in at least half the years.
        One-off spike = not recurring, but a single year holds 20% or more of that date's total.
        Everything else is Mixed. This is a rough heuristic, not a statistical test.</p>
    </section>

    <section class="panel wide">
      <h2>Date detail: <span id="detailName"></span></h2>
      <p class="sub">
        Explore any date: <select id="dateSelect"></select>
        &nbsp; Bars are sightings per year; the line is the typical day.
      </p>
      <div class="chart"><canvas id="cDetail"></canvas></div>
    </section>

    <section class="panel"><h2>By month</h2><p class="sub">Summer usually peaks.</p>
      <div class="chart"><canvas id="cMonth"></canvas></div></section>
    <section class="panel" id="hourPanel"><h2>By hour of day</h2><p class="sub">Local time of the sighting.</p>
      <div class="chart"><canvas id="cHour"></canvas></div></section>
    <section class="panel" id="shapePanel"><h2>Most reported shapes</h2><p class="sub">As typed by witnesses.</p>
      <div class="chart"><canvas id="cShape"></canvas></div></section>
    <section class="panel" id="statePanel"><h2>Top states (raw counts)</h2>
      <p class="sub">Not adjusted for population, so big states dominate.</p>
      <div class="chart"><canvas id="cState"></canvas></div></section>
  </div>
</main>

<script>
const D = __DATA__;

if (typeof Chart === 'undefined') {
  document.getElementById('nochart').style.display = 'block';
} else {
  Chart.defaults.color = '#9aa8cc';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.07)';
  const ACC = '#7cf5c4', ACC2 = '#8ea2ff', WARN = '#ffb86b';
  const S = D.summary;

  // Summary cards
  const cards = [
    ['Total sightings', S.total.toLocaleString()],
    ['Date range', S.first.slice(0, 4) + ' to ' + S.last.slice(0, 4)],
    ['Typical day (avg)', S.typical],
    ['Busiest day', S.topDay + ' (' + S.topAvg + ')'],
  ];
  document.getElementById('cards').innerHTML = cards.map(function (c) {
    return '<div class="card"><div class="k">' + c[0] + '</div><div class="v">' + c[1] + '</div></div>';
  }).join('');
  document.getElementById('dailySub').textContent =
    'Averaged over ' + S.startYear + '-' + S.endYear + ', counting years with zero sightings. Typical day: ' + S.typical + '.';
  document.getElementById('topSub').textContent =
    'Same top dates as before, now split by year (' + S.startYear + '-' + S.endYear + ').';

  function bar(id, labels, values, horizontal, color) {
    return new Chart(document.getElementById(id), {
      type: 'bar',
      data: { labels: labels, datasets: [{ data: values, backgroundColor: color || ACC2, borderRadius: 3 }] },
      options: { indexAxis: horizontal ? 'y' : 'x', maintainAspectRatio: false,
                 plugins: { legend: { display: false } } }
    });
  }

  new Chart(document.getElementById('cYear'), {
    type: 'line',
    data: { labels: D.perYear.labels, datasets: [{ data: D.perYear.values, borderColor: ACC,
            backgroundColor: 'rgba(124,245,196,0.12)', fill: true, tension: 0.25, pointRadius: 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
               scales: { x: { ticks: { maxTicksLimit: 14 } } } }
  });

  new Chart(document.getElementById('cDaily'), {
    type: 'line',
    data: { labels: D.daily.labels, datasets: [{ data: D.daily.values, borderColor: ACC2,
            tension: 0.15, pointRadius: 0, borderWidth: 1.5 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { ticks: { autoSkip: false, maxRotation: 0, callback: function (v) {
        var l = this.getLabelForValue(v);
        return l.slice(-2) === ' 1' ? l.split(' ')[0] : '';
      } } } } }
  });

  bar('cMonth', D.month.labels, D.month.values, false, ACC2);
  if (D.hour) { bar('cHour', D.hour.labels, D.hour.values, false, ACC); }
  else { document.getElementById('hourPanel').style.display = 'none'; }
  if (D.shapes) { bar('cShape', D.shapes.labels, D.shapes.values, true, ACC2); }
  else { document.getElementById('shapePanel').style.display = 'none'; }
  if (D.states) { bar('cState', D.states.labels, D.states.values, true, ACC); }
  else { document.getElementById('statePanel').style.display = 'none'; }

  // Detail chart for a chosen date
  const detail = new Chart(document.getElementById('cDetail'), {
    data: { labels: D.years, datasets: [
      { type: 'bar', data: [], backgroundColor: WARN, borderRadius: 3, order: 2 },
      { type: 'line', data: D.years.map(function () { return D.typical; }),
        borderColor: ACC, borderDash: [6, 4], pointRadius: 0, order: 1 }
    ] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } } }
  });

  const select = document.getElementById('dateSelect');
  D.daily.keys.forEach(function (k, i) {
    const o = document.createElement('option');
    o.value = k; o.textContent = D.daily.labels[i];
    select.appendChild(o);
  });

  function showDate(md) {
    const i = D.daily.keys.indexOf(md);
    document.getElementById('detailName').textContent = D.daily.labels[i];
    detail.data.datasets[0].data = D.days[md];
    detail.update();
    select.value = md;
    document.querySelectorAll('#topBody tr').forEach(function (tr) {
      tr.classList.toggle('sel', tr.dataset.md === md);
    });
  }
  select.addEventListener('change', function () { showDate(select.value); });

  // Top-days table
  const body = document.getElementById('topBody');
  D.top.forEach(function (r) {
    const tr = document.createElement('tr');
    tr.dataset.md = r.md;
    const cls = r.verdict === 'One-off spike' ? 'One-off' : r.verdict;
    [r.label, r.avg, r.peakYear, r.peakCount, r.peakShare + '%',
     r.yearsAbove + ' of ' + D.years.length].forEach(function (v) {
      const td = document.createElement('td'); td.textContent = v; tr.appendChild(td);
    });
    const td = document.createElement('td');
    const span = document.createElement('span');
    span.className = 'tag ' + cls; span.textContent = r.verdict;
    td.appendChild(span); tr.appendChild(td);
    tr.addEventListener('click', function () { showDate(r.md); });
    body.appendChild(tr);
  });

  showDate(D.top.length ? D.top[0].md : D.daily.keys[0]);
}
</script>
</body>
</html>
"""


def main(path):
    data = build_data(path)
    payload = json.dumps(data).replace("</", "<\\/")
    OUT_FILE.write_text(HTML.replace("__DATA__", payload), encoding="utf-8")
    print(f"Wrote {OUT_FILE.resolve()}")
    print("Top days:")
    for r in data["top"]:
        print(f"  {r['label']:>7}  avg {r['avg']:>5}  peak {r['peakYear']} ({r['peakShare']}%)  {r['verdict']}")
    webbrowser.open(OUT_FILE.resolve().as_uri())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])