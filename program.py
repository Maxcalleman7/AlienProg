import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

OUT = Path("nuforc_out")
OUT.mkdir(exist_ok=True)

# Column-name candidates, since NUFORC exports differ.
CANDIDATES = {
    "time": ["reported_date_time", "datetime", "date_time", "Date / Time", "date", "occurred"],
    "shape": ["shape", "Shape"],
    "city": ["city", "City"],
    "state": ["state", "State"],
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon", "lng"],
}


def pick(df, key):
    for c in CANDIDATES[key]:
        if c in df.columns:
            return c
    return None


def load(path):
    df = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    cols = {k: pick(df, k) for k in CANDIDATES}
    print("Detected columns:", cols)
    if cols["time"] is None:
        sys.exit(f"No time column found. Columns are: {list(df.columns)}")
    df["t"] = pd.to_datetime(df[cols["time"]], errors="coerce")
    df = df.dropna(subset=["t"])
    df = df[(df.t.dt.year >= 1940) & (df.t.dt.year <= pd.Timestamp.now().year)]
    return df, cols


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print("wrote", OUT / name)


def main(path):
    df, cols = load(path)
    print(f"{len(df):,} sightings, {df.t.min().date()} to {df.t.max().date()}")

    # 1. Sightings per year
    fig, ax = plt.subplots(figsize=(9, 4))
    df.groupby(df.t.dt.year).size().plot(ax=ax)
    ax.set_title("Sightings per year")
    save(fig, "per_year.png")

    # 2. Hour of day (skip if timestamps are date-only)
    if (df.t.dt.hour != 0).any():
        fig, ax = plt.subplots(figsize=(8, 4))
        df.groupby(df.t.dt.hour).size().plot.bar(ax=ax)
        ax.set_title("Sightings by hour of day (local time)")
        save(fig, "by_hour.png")

    # 3. Seasonality
    fig, ax = plt.subplots(figsize=(8, 4))
    df.groupby(df.t.dt.month).size().plot.bar(ax=ax)
    ax.set_title("Sightings by month")
    save(fig, "by_month.png")

    # 4. Holiday spikes: compare fireworks days to a typical day.
    daily = df.groupby(df.t.dt.date).size()
    daily.index = pd.to_datetime(daily.index)
    md = daily.index.strftime("%m-%d")
    typical = daily.groupby(md).mean()
    print("\nTop 10 calendar days by average sightings:")
    print(typical.sort_values(ascending=False).head(10).round(1))
    print(f"Median calendar day: {typical.median():.1f}")

    # 5. Shapes
    if cols["shape"]:
        fig, ax = plt.subplots(figsize=(8, 5))
        df[cols["shape"]].str.lower().value_counts().head(15).sort_values().plot.barh(ax=ax)
        ax.set_title("Most reported shapes")
        save(fig, "shapes.png")

    # 6. Top states
    if cols["state"]:
        fig, ax = plt.subplots(figsize=(8, 5))
        df[cols["state"]].value_counts().head(15).sort_values().plot.barh(ax=ax)
        ax.set_title("Sightings by state/region (raw counts)")
        save(fig, "states.png")

    # 7. Map, if coordinates exist
    if cols["lat"] and cols["lon"]:
        g = df.dropna(subset=[cols["lat"], cols["lon"]])
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.scatter(g[cols["lon"]], g[cols["lat"]], s=1, alpha=0.1)
        ax.set_title("Sighting locations")
        save(fig, "map.png")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])