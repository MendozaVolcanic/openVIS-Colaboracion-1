# Bugs found in openVIS during Southern Andes adaptation

This document records bugs found in the upstream code while running case
studies on Chilean volcanoes. Useful for a future contribution back upstream
(`rdnegri/openVIS`).

---

## Bug 1 — Volcano names containing commas are silently corrupted

**File:** `src/db_vis.py`, line 338
**Severity:** Medium (silent data corruption — affects multiple GVP entries)

### Description

In `get_volcanoes_from_gvp_database()`, after loading the volcanoes CSV,
the code does:

```python
# Create escape character for sql request
volcanoes.replace("'", "''", regex=True, inplace=True)
# replace coma by points in number
volcanoes.replace(",", ".", regex=True, inplace=True)
```

The intent (per the comment) is to convert comma decimal separators to
points in numeric columns. However, `DataFrame.replace(',', '.', regex=True)`
applies the substitution to **every string column**, including
`Volcano Name`, `Country`, `Region`, etc.

This silently mangles any volcano whose name contains a comma:

| GVP name           | After replace      |
|--------------------|--------------------|
| Hudson, Cerro      | Hudson. Cerro      |
| Negrillar, La      | Negrillar. La      |
| Tujle, Cerro       | Tujle. Cerro       |
| Hierro, El         | Hierro. El         |
| Soufrière, La      | Soufrière. La      |
| ...                | ...                |

When the user lists `'Hudson, Cerro'` in their TOML config, the lookup
`volcs[volcs['Volcano Name'] == 'Hudson, Cerro']` returns 0 rows because
the in-memory dataframe has `'Hudson. Cerro'` instead. The error
manifests as:

```
WARNING [db_vis.py:223] No volcano found in database for Hudson, Cerro - Skipping
```

### Reproduction

1. Use `cfg/volcanoes.csv` as shipped (Smithsonian GVP export).
2. In TOML config: `VolcanoesList = ['Hudson, Cerro']`
3. Run `src/vis_main.py`.
4. Observe the "No volcano found" warning and empty results.

### Suggested fix

Apply the comma → point replacement only to numeric-as-string columns
(or, since the dtype-aware `read_csv` is already using `decimal=','`,
remove the global replace altogether):

```python
# Old (buggy):
volcanoes.replace(",", ".", regex=True, inplace=True)

# Option A — restrict to known numeric-as-text columns
for col in ["Latitude", "Longitude", "Elevation (m)"]:
    if volcanoes[col].dtype == object:
        volcanoes[col] = volcanoes[col].str.replace(",", ".", regex=False)

# Option B — drop entirely; pandas already handled it via decimal=','
# in read_csv (line 305).
```

### Workaround used in this fork

In `cfg/hudson_2011.toml`, the volcano is listed as `'Hudson. Cerro'`
(with the same corruption applied) so the post-replace lookup matches.
This is a hack — the proper fix is upstream.

---

## Bug 2 — `vis_main.py` ignores `--config` CLI argument

**File:** `src/vis_main.py` / `settings.py`
**Severity:** Low (workflow inconvenience)

### Description

`vis_main.py` accepts no command-line arguments. The config path is
hardcoded in `settings.py`:

```python
config = toml.load(join(BASE_DIR, 'cfg', 'vis_config.toml'))
```

Workaround: copy the desired config to `vis_config.toml` before each run.
This makes batch scripts (e.g. `dazim_sweep.py`) verbose and error-prone.

### Suggested fix

Accept `--config <path>` via `argparse` in `vis_main.py` and pass it down
to `settings.py`.
