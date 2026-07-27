# fig_recc

A small sampling pipeline that filters city neighbourhood data against configurable scenario
constraints and exports the results in a format consumable by [RECC](https://github.com/IndEcol/RECC-ODYM).
Written by Keagan H. Rankin as part of a 2026 IRP project.

## What it does

Given a set of neighbourhoods (housing units with type, floor area, population, age cohort, etc.)
and a scenario config, `FIGRECCSampler` finds the subset of neighbourhoods that meet the scenario's
constraints for each modelled time period, then summarizes and exports that subset (current housing
stock by age cohort, m² per person over time, housing type split) as RECC-formatted CSVs.

## Requirements

Python 3.12. Third-party dependencies: `pandas`, `numpy`, `scipy`, `tqdm`, `pyyaml`.

```
pip install pandas numpy scipy tqdm pyyaml
```

## Usage

Run the entry-point script from the project root. With no arguments it runs **every**
`input_files/params*.yaml` it finds:

```
python main.py
```

Or name one or more scenarios to run just those:

```
python main.py params_s1_maxsfh.yaml
```

For each scenario this loads its params file via `Config`, filters neighbourhoods per model period
via `FIGRECCSampler.get_subset_all_periods()`, and writes the RECC-formatted CSVs via
`output_to_recc()`. Each scenario gets its own output folder, `data_cache/<scenario_name>/`, so the
RECC filenames stay exact and scenarios never overwrite each other:

```
data_cache/
  s0_reference/
    2_S_RECC_FinalProducts_2015_resbuildings_Cities_V1.0.csv
    3_SHA_TypeSplit_Buildings.csv
    mat_floor_split.csv
    ...
  s1_maxsfh/
    ...same filenames...
```

If one scenario fails (e.g. its constraints exclude every neighbourhood) the rest still run; failures
are listed in the closing summary and the script exits non-zero.

## Adding a scenario

Copy an existing params file to a new `input_files/params_<something>.yaml`, set its `scenario_name`,
and edit whatever differs. Scenario files are standalone — each one is complete in itself rather than
inheriting from a base — and `main.py` picks up the new file automatically.

## Configuration

Each scenario is one `input_files/params*.yaml` file (see
[`input_files/params.yaml`](input_files/params.yaml) for the reference scenario):

- `scenario_name` — names the scenario's output folder under `data_cache/`. Defaults to the params
  filename stem if omitted.
- `model_periods` / `base_year` / `period_step` — the time periods to sample for.
- `pop`, `m2_per_p`, `neighbourhoods` — relative paths (under `input_files/`) to the scenario's
  population, m²-per-person, and neighbourhood reference data.
- `constraints` — the conditions a neighbourhood must meet to stay in the sample for a given period.
  A few baseline constraints (`need_cond`, `min_sfh_share`, `min_mfh_share`, `max_sfh_share`,
  `max_mfh_share`) are handled directly by the sampler. Any other key is treated as an arbitrary
  constraint and just needs:
  ```yaml
  my_constraint:
    col: 'some_column'   # column in the neighbourhoods table
    limit: 3              # threshold value
    extrema: 'min'         # 'min' or 'max'
    collator: 'mean'       # how to aggregate the column per neighbourhood
  ```
  so new constraints can usually be added via YAML alone, without touching `sampler.py`.

Shared reference data lives under `input_files/<dataset_name>/` (see
`input_files/iloilo_scenar_reference/` for the current example) and can be pointed at by any number
of scenarios. Generated outputs are written to `data_cache/<scenario_name>/`, which is created
automatically and is safe to delete/regenerate.