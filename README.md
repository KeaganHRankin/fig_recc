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

Run the entry-point script from the project root:

```
python main.py
```

This loads `input_files/params.yaml` via `Config`, filters neighbourhoods per model period via
`FIGRECCSampler.get_subset_all_periods()`, and writes the RECC-formatted CSVs to `data_cache/` via
`output_to_recc()`.

## Configuration

All scenario setup lives in [`input_files/params.yaml`](input_files/params.yaml):

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

Scenario reference data lives under `input_files/<scenario_name>/` (see
`input_files/iloilo_scenar_reference/` for the current example). Generated outputs are written to
`data_cache/`, which is created automatically and is safe to delete/regenerate.