# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

FIG-RECC is a small research pipeline (2026 IRP project, Keagan H. Rankin) that samples city
neighbourhood data against scenario constraints and exports the results in a format consumable by
RECC. It runs any number of scenarios in one batch, each defined by its own params yaml. It's a git
repository (MIT licensed) with two Python modules plus an entry-point script, but still no test
suite, no dependency manifest, and no build tooling — don't assume any of that infrastructure exists.

Runtime: Python 3.12, run via the `data_sci_pytwelve` conda environment on this machine
(`C:\Users\keaga\miniconda3\envs\data_sci_pytwelve\python.exe`) — the bare `python`/`py` on PATH is
just a Windows Store alias stub and won't run anything. Third-party imports used across the
codebase: `pandas`, `numpy`, `scipy`, `tqdm`, `pyyaml`. There's no requirements/environment file, so
if a dependency is missing it needs to be installed manually into that env
(`pip install pandas numpy scipy tqdm pyyaml`).

`main.py` is the entry point and is a **multi-scenario batch runner**. With no CLI args it runs every
`input_files/params*.yaml`; with args it runs just the named ones. Per scenario it does:

```python
config = Config(params_file)
sampler = FIGRECCSampler(config)
sampler.get_subset_all_periods()
sampler.output_to_recc()
```

Run it with `& "C:\Users\keaga\miniconda3\envs\data_sci_pytwelve\python.exe" main.py [params_x.yaml ...]`
(or `python main.py` once a real Python is on PATH). Those four lines can also be run ad hoc from a
Python shell/notebook if only partial output is needed.

Scenario failures are caught per-scenario so one bad config doesn't abort the batch; failures are
listed in the closing summary and `main` returns 1. This matters because `get_subset_period` raises
`ValueError` whenever a scenario's constraints exclude every neighbourhood — a normal outcome when
sweeping constraint values, not necessarily a bug.

## Architecture

### `config.py` — `Config`

`Config(params_file="params.yaml")` represents **one scenario**. Each instance holds its own state,
so any number of scenarios can be loaded side by side in a single process:

- Reads `input_files/<params_file>` into `self.params`.
- Loads three reference tables named in that file (`pop`, `m2_per_p`, `neighbourhoods`) as
  `self.population`, `self.m2_per_p`, `self.neighbourhoods`.
- Resolves `self.scenario` from the yaml's `scenario_name` key, falling back to the params filename
  stem, and creates the scenario's output dir `self.cache_dir` = `data_cache/<scenario>/`.
- Class-level (shared, static) attributes: `input_files`, `cache_root`, and `constraint_bline` — the
  fixed list of "baseline" constraint keys (`need_cond`, `min_sfh_share`, `min_mfh_share`,
  `max_sfh_share`, `max_mfh_share`) handled by dedicated sampler logic, as opposed to arbitrary
  constraints (see below).

Two things to preserve when editing:

- **`cache_dir` must keep its trailing `/`** — `sampler.py` builds output paths by string
  concatenation (`self.config.cache_dir+recc_resvars[0]`), not `os.path.join`.
- **Do not reintroduce the singleton.** This class *was* a singleton (`__new__` returning a cached
  `_instance`, with all attributes assigned onto the class). That made batch runs silently return the
  first scenario's data for every subsequent scenario, and was removed for exactly that reason.

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
   they read `self.n_subset`. `output_to_recc` writes three RECC-named CSVs into the scenario's
   `config.cache_dir` (`data_cache/<scenario>/`), then calls `output_extra_splits()`:
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
`params*.yaml` and the `*_test.xlsx` fixtures — so every scenario config is tracked, while the
reference data under `input_files/iloilo_scenar_reference/` and the root-level
`input_files/*.csv`/`.xlsx` files are intentionally untracked. Keep new *data* out of git unless the
ignore rules are deliberately changed; new *scenario yamls* are picked up automatically (note the
glob is `params*.yaml`, so a scenario file named otherwise would be silently ignored).

## Data model

- `neighbourhoods` CSV (e.g. `input_files/iloilo_scenar_reference/nb_iloilo.csv`): one row per
  building/unit, keyed by `n_id` (neighbourhood) with `htype` (`sfh`/`mfh`), `m2`, `pop`,
  `age_cohort`, `in_city`, plus arbitrary extra columns that can be referenced by name from
  arbitrary constraints in `params.yaml`.
- `m2_per_person` CSV: `period, res, nonres` — target m² per person by model period, used for the m²
  sufficiency constraint and as a direct RECC export.
- `population` CSV: `period, pop`.
- Shared reference data lives under `input_files/<dataset_name>/` (currently only
  `iloilo_scenar_reference/`); each params yaml selects which files to load by relative path, and
  several scenarios can point at the same dataset. The root-level `input_files/*.csv` and
  `*_test.xlsx` files are not referenced by any current params file and appear to be alternate/test
  fixtures rather than active inputs.
- Each `input_files/params*.yaml` is the single source of truth for one scenario: its
  `scenario_name` (output folder), model periods, base year, which data files to load, the full
  constraint set (baseline + arbitrary), and `extra_splits` (a plain list of `neighbourhoods` columns
  to export as extra per-column split CSVs — see above). Scenario files are **standalone**, not
  inheriting from a base, so each is complete and readable on its own; add a scenario by copying an
  existing file (e.g. `params_s1_maxsfh.yaml`) and editing it. When adding a new constraint, prefer
  extending the YAML `constraints` block over adding a new bespoke method to `FIGRECCSampler`, unless
  the constraint needs logic that doesn't fit the `{col, limit, extrema, collator}` shape.
- `data_cache/<scenario>/` holds each scenario's generated outputs; created automatically by `Config`
  and safe to delete/regenerate. RECC filenames are kept **exact and unprefixed** inside each folder
  (that's why scenarios are separated by directory rather than filename prefix), so outputs are
  directly RECC-ingestible. Any leftover flat `*.csv` / hand-made `s0_*.csv` files in the
  `data_cache/` root predate the per-scenario layout and are stale.
