# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

FIG-RECC is a small research pipeline (2026 IRP project, Keagan H. Rankin) that samples city
neighbourhood data against scenario constraints and exports the results in a format consumable by
RECC. It's a git repository (MIT licensed) with two Python modules plus an entry-point script, but
still no test suite, no dependency manifest, and no build tooling — don't assume any of that
infrastructure exists.

Runtime: Python 3.12, run via the `data_sci_pytwelve` conda environment on this machine
(`C:\Users\keaga\miniconda3\envs\data_sci_pytwelve\python.exe`) — the bare `python`/`py` on PATH is
just a Windows Store alias stub and won't run anything. Third-party imports used across the
codebase: `pandas`, `numpy`, `scipy`, `tqdm`, `pyyaml`. There's no requirements/environment file, so
if a dependency is missing it needs to be installed manually into that env
(`pip install pandas numpy scipy tqdm pyyaml`).

`main.py` is the entry point:

```python
from config import Config
from sampler import FIGRECCSampler

def main():
    config = Config()
    sampler = FIGRECCSampler(config)
    sampler.get_subset_all_periods()
    sampler.output_to_recc()
```

Run it with `& "C:\Users\keaga\miniconda3\envs\data_sci_pytwelve\python.exe" main.py` (or
`python main.py` once a real Python is on PATH). The same three lines can also be run ad hoc from a
Python shell/notebook if only partial output is needed.

## Architecture

### `config.py` — `Config`

Singleton (`__new__` returns the same instance every time) that loads all scenario inputs once at
first instantiation:

- Reads `input_files/params.yaml` into `Config.params`.
- Loads three reference tables named in `params.yaml` (`pop`, `m2_per_p`, `neighbourhoods`) as
  `Config.population`, `Config.m2_per_p`, `Config.neighbourhoods`.
- Exposes `Config.constraint_bline`, the fixed list of "baseline" constraint keys
  (`need_cond`, `min_sfh_share`, `min_mfh_share`, `max_sfh_share`, `max_mfh_share`) that are
  handled by dedicated logic in the sampler, as opposed to arbitrary constraints (see below).
- Creates `data_cache/` on disk if it doesn't already exist.

Because it's a singleton, mutating `Config.params` (or any other class attribute) after the first
instantiation affects every subsequent `Config()` call in the process — there is no way to load a
second, differently-configured instance side by side without resetting `Config._instance`.

### `sampler.py` — `FIGRECCSampler`

Takes a `Config` instance and works with a copy of `config.neighbourhoods` (`self.n_df`), adding a
derived `m2_per_` (m² per person) column.

Method groups (in file order):

1. **Sample limiting methods** (`limit_arbitrary`, `limit_m2`, `limit_htype`, `get_limited_htype`,
   `get_subset_period`, `get_subset_all_periods`) — for each model period in
   `params.yaml: model_periods`, filter `n_df` down to the neighbourhoods (`n_id`) that satisfy all
   configured constraints, storing the result in `self.n_subset[period]`. Constraints come from two
   places:
   - **Baseline constraints** (`config.constraint_bline`): m² sufficiency per period
     (`m2_per_person.csv`) and min/max single-/multi-family housing share, handled by dedicated
     `limit_m2` / `limit_htype` calls.
   - **Arbitrary constraints**: any other key under `params.yaml: constraints` is treated as a
     generic `{col, limit, extrema, collator}` spec and dispatched through `limit_arbitrary`,
     letting new constraints be added purely via YAML without code changes.
   - All limiting methods return **excluded** neighbourhood ids; the excluded sets are subtracted
     from the running candidate set via `np.setdiff1d`. `get_subset_period` raises `ValueError` if a
     period ends up with zero eligible neighbourhoods.

2. **Sample summary methods** (`get_res_current_stock`, `get_res_typesplit`, `get_x_split`,
   `output_extra_splits`, `output_to_recc`) — must be called after `get_subset_all_periods()` since
   they read `self.n_subset`. `output_to_recc` writes three RECC-named CSVs into `Config.cache_dir`
   (`data_cache/`), then calls `output_extra_splits()`:
   - `2_S_RECC_FinalProducts_2015_resbuildings_Cities_V1.0.csv` (current stock by age cohort/htype)
   - `2_S_RECC_FinalProducts_Future_resbuildings_Cities_V1.0.csv` (m² per person time series)
   - `3_SHA_TypeSplit_Buildings.csv` (housing type split per period)
   - `<column>_split.csv` for each column listed in `params.yaml: extra_splits` — a thin wrapper
     around `get_x_split(col)` that lets new per-column split exports be added purely via YAML,
     without writing a new method or touching `output_to_recc` (mirrors the arbitrary-constraint
     pattern above).

3. **Random sampling methods** (`counter`, `random_sample_n`) — **incomplete/WIP**. `counter`
   references `self.pop_df`, which is never set (it's commented out in `__init__`) and uses invalid
   pandas indexing (`self.pop_df[cond, col]` instead of `.loc[cond, col]`); calling it will raise.
   Don't assume this section works without fixing it first.

## Repository

Git repo (branch `master`, tracked against `origin`), MIT licensed (see `LICENSE`). `.gitignore`
excludes `data_cache/`, `__pycache__/`, and everything under `input_files/` **except**
`params.yaml` and the `*_test.xlsx` fixtures — the active scenario data under
`input_files/iloilo_scenar_reference/` and the root-level `input_files/*.csv`/`.xlsx` files are
intentionally untracked. Keep new scenario data out of git unless the ignore rules are deliberately
changed.

## Data model

- `neighbourhoods` CSV (e.g. `input_files/iloilo_scenar_reference/nb_iloilo.csv`): one row per
  building/unit, keyed by `n_id` (neighbourhood) with `htype` (`sfh`/`mfh`), `m2`, `pop`,
  `age_cohort`, `in_city`, plus arbitrary extra columns that can be referenced by name from
  arbitrary constraints in `params.yaml`.
- `m2_per_person` CSV: `period, res, nonres` — target m² per person by model period, used for the m²
  sufficiency constraint and as a direct RECC export.
- `population` CSV: `period, pop`.
- Scenario-specific reference data lives under `input_files/<scenario_name>/` (currently only
  `iloilo_scenar_reference/`); `params.yaml` selects which scenario's files to load by relative path.
  The root-level `input_files/*.csv` and `*_test.xlsx` files are not referenced by the current
  `params.yaml` and appear to be alternate/test fixtures rather than active inputs.
- `input_files/params.yaml` is the single source of truth for: model periods, base year, which
  scenario data files to load, the full constraint set (baseline + arbitrary), and `extra_splits`
  (a plain list of `neighbourhoods` columns to export as extra per-column split CSVs — see above).
  When adding a new constraint, prefer extending the YAML `constraints` block over adding a new
  bespoke method to `FIGRECCSampler`, unless the constraint needs logic that doesn't fit the
  `{col, limit, extrema, collator}` shape.
- `data_cache/` holds generated outputs; it's created automatically by `Config` if missing and can be
  treated as disposable/regeneratable. It still contains some hand-produced files prefixed `s0_`
  (e.g. `s0_number_of_floors.csv`, `s0_floor_material.csv`) predating `output_extra_splits` — those
  are historical references, not generated by current code, and are gitignored along with the rest
  of `data_cache/`.
