"""Convert NUFORC's UTC timestamps to the witness's local wall-clock time.

The export only has a state/province and a country code, so each row gets the
main time zone of its state (US, Canada) or country. States that span two zones
use the zone most people live in, so a few border towns will be off by an hour.
Rows we can't place stay in UTC.
"""

import pandas as pd

US_STATES = {
    "America/New_York": ["CT", "DC", "DE", "FL", "GA", "KY", "MA", "MD", "ME", "NC", "NH",
                         "NJ", "NY", "OH", "PA", "RI", "SC", "VA", "VT", "WV"],
    "America/Detroit": ["MI"],
    "America/Indiana/Indianapolis": ["IN"],
    "America/Chicago": ["AL", "AR", "IA", "IL", "KS", "LA", "MN", "MO", "MS", "ND", "NE",
                        "OK", "SD", "TN", "TX", "WI"],
    "America/Denver": ["CO", "MT", "NM", "UT", "WY"],
    "America/Boise": ["ID"],
    "America/Phoenix": ["AZ"],
    "America/Los_Angeles": ["CA", "NV", "OR", "WA"],
    "America/Anchorage": ["AK"],
    "Pacific/Honolulu": ["HI"],
    "America/Puerto_Rico": ["PR"],
}

CA_PROVINCES = {
    "America/St_Johns": ["NL"],
    "America/Halifax": ["NB", "NS", "PE"],
    "America/Toronto": ["ON", "QC"],
    "America/Winnipeg": ["MB"],
    "America/Regina": ["SK"],
    "America/Edmonton": ["AB"],
    "America/Vancouver": ["BC"],
    "America/Whitehorse": ["YT"],
    "America/Yellowknife": ["NT"],
    "America/Iqaluit": ["NU"],
}

# Countries outside North America that are (mostly) a single zone, or where one
# zone covers most of the population.
COUNTRIES = {
    "GB": "Europe/London", "IE": "Europe/Dublin", "PT": "Europe/Lisbon",
    "NL": "Europe/Amsterdam", "DE": "Europe/Berlin", "BE": "Europe/Brussels",
    "FR": "Europe/Paris", "ES": "Europe/Madrid", "IT": "Europe/Rome",
    "SE": "Europe/Stockholm", "NO": "Europe/Oslo", "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki", "PL": "Europe/Warsaw", "HR": "Europe/Zagreb",
    "GR": "Europe/Athens", "TR": "Europe/Istanbul", "IL": "Asia/Jerusalem",
    "ZA": "Africa/Johannesburg", "IN": "Asia/Kolkata", "PK": "Asia/Karachi",
    "MY": "Asia/Kuala_Lumpur", "PH": "Asia/Manila", "JP": "Asia/Tokyo",
    "NZ": "Pacific/Auckland", "AU": "Australia/Sydney", "MX": "America/Mexico_City",
    "BR": "America/Sao_Paulo",
}


def _lookup():
    table = {}
    for country, zones in (("US", US_STATES), ("CA", CA_PROVINCES)):
        for tz, codes in zones.items():
            for code in codes:
                table[(country, code)] = tz
    return table


REGION_TZ = _lookup()


def zone_for(country, state):
    """Best-guess IANA zone name for one row, or None if unknown."""
    return REGION_TZ.get((country, state)) or COUNTRIES.get(country)


def to_local(t, state=None, country=None):
    """Return naive local times for a Series of UTC timestamps.

    Timestamps that are already naive are assumed to be local and are returned
    unchanged. Without a country column, rows are treated as US.
    """
    if t.dt.tz is None:
        return t
    st = state.astype(str).str.upper().str.strip() if state is not None else pd.Series("", index=t.index)
    co = country.astype(str).str.upper().str.strip() if country is not None else pd.Series("US", index=t.index)
    zones = pd.Series([zone_for(c, s) for c, s in zip(co, st)], index=t.index)

    local = t.dt.tz_convert("UTC").dt.tz_localize(None)  # fallback: UTC wall clock
    for tz, idx in zones.dropna().groupby(zones.dropna()).groups.items():
        local.loc[idx] = t.loc[idx].dt.tz_convert(tz).dt.tz_localize(None)
    unplaced = zones.isna().sum()
    if unplaced:
        print(f"Note: {unplaced:,} rows have no known time zone and stay in UTC.")
    return local
