"""
Ingest raw PSA CPH PUF census data into a fig_recc neighbourhoods.csv.
Written by Keagan H. Rankin 2026 IRP project

Adapted from modelling data/iloilo/iloilo_exp_4_creating_figrecc_input.ipynb.
Run from the repo root:
    python ingest/ph_census_ingest.py                     # every ingest/ingest_*.yaml
    python ingest/ph_census_ingest.py ingest_iloilo.yaml  # just the named config(s)
    python ingest/ph_census_ingest.py --force             # allow overwriting existing output
"""

import glob
import os
import sys

import numpy as np
import pandas as pd
import yaml

# no package tooling in this repo; keep the path shim explicit.
_THIS_DIR = os.path.realpath(os.path.dirname(__file__)) + "/"
_REPO_ROOT = os.path.realpath(_THIS_DIR + "..") + "/"
sys.path.insert(0, _REPO_ROOT)

from config import Config  # noqa: E402  (import needs the path shim above)


###########################
### CPH 2020 FORM 2 SPEC ###
# these are the same for every philippine city, so they live in code rather than per-dataset yaml.

# id columns forming the psgc2021 barangay key. the puf files already zero-pad these
# ('06', '310', '00', '001'), so they must be read as strings - pandas would otherwise infer
# int64 and strip the padding, corrupting the key.
ID_COLS = ['REG', 'PRV', 'MUN', 'BGY']
ID_DTYPES = {c: str for c in ID_COLS}

# census column -> neighbourhoods column
COL_RENAME = {'B1': 'htype', 'D1': 'm2', 'B8': 'age_cohort',
              'B2': 'n_floors', 'B3': 'mat_roof', 'B4': 'mat_wall', 'B5': 'finish_floor',
              'B6': 'mat_floor', 'B7': 's.o.repair', 'URB': 'urban'}

# columns whose values are labels read straight out of the metadata valuesets.
# URB is included so 'urban' reads 'Urban'/'Rural' rather than the raw 1/2 codes.
LABEL_COLS = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'URB']

# B1 type of building -> rasmi classes -> recc classes
B1_MAP = {1: 'RS', 2: 'RM', 3: 'RM', 4: 'RM', 5: 'RM', 6: 'NR', 7: 'NR', 8: 'RS', 9: 'RS', 0: 'RS'}
RASMI_TO_RECC = {'RS': 'sfh', 'RM': 'mfh', 'NR': 'oth'}

# D1 floor area code -> band -> midpoint m2.
# hardcoded, not parsed: the metadata only carries text labels ("120 - 149 sq.m. or ...").
D1_MAP = {1: [0, 5], 2: [5, 9], 3: [10, 19], 4: [20, 29], 5: [30, 49], 6: [50, 69], 7: [70, 89],
          8: [90, 119], 9: [120, 149], 10: [150, 199], 11: [200, 350], 99: [0, 350]}
D1_MEAN = {k: float(np.mean(v)) for k, v in D1_MAP.items()}

# B8 year built code -> age cohort [lo, hi]. hardcoded for the same reason as D1.
B8_MAP = {1: [2020, 2020], 2: [2019, 2019], 3: [2018, 2018], 4: [2017, 2017], 5: [2016, 2016],
          6: [2011, 2015], 7: [2001, 2010], 8: [1991, 2000], 9: [1981, 1990], 10: [1900, 1980],
          11: [1900, 2020], 99: [1900, 2020]}

# output column order, must match what sampler.py expects.
OUT_COLS = list(COL_RENAME.values()) + ['n_id', 'HUSN', 'HSN', 'pop', 'in_city']

# households with this serial number are 'homeless'/poorly-defined and get dropped.
HSN_DROP = 999999


######################
### METADATA READER ###
def read_valueset(meta, code):
    """
    get the {census code: label} map for one column out of the metadata valueset sheet.

    the sheet delimits each block with a '<CODE>_VS1' marker in its first column, so any
    column in any CPH PUF file can be looked up by name instead of by hardcoded row offsets.
    """
    marker = meta.iloc[:, 0]
    starts = marker.dropna()

    hits = starts.index[starts == f"{code}_VS1"]
    if len(hits) == 0:
        raise KeyError(f"no valueset '{code}_VS1' in metadata sheet")
    i0 = hits[0]

    # block runs to the next marker (or the end of the sheet).
    later = starts.index[starts.index > i0]
    i1 = later[0] if len(later) else len(meta)

    # col 2 holds the label, col 3 the census code. drop the trailing blank separator row.
    block = meta.iloc[i0 + 1:i1, [2, 3]].dropna(subset=[meta.columns[3]])
    return dict(zip(block.iloc[:, 1], block.iloc[:, 0]))


def load_valuesets(cfg):
    """read every valueset needed by LABEL_COLS from the metadata workbook."""
    meta_cfg = cfg['metadata']
    meta = pd.read_excel(resolve_data(cfg, meta_cfg['path']),
                         sheet_name=meta_cfg.get('sheet', 'cph_2020_f2_valueset'))

    return {c: read_valueset(meta, c) for c in LABEL_COLS}


################
### CLEANING ###
def make_psgc(df):
    """
    build the psgc2021 barangay key from the census id columns.

    relies on ID_COLS having been read as strings (see ID_DTYPES) so the file's own
    zero-padding is preserved - no widths are assumed or re-imposed here.
    """
    df = df.copy()
    df['psgc2021'] = df[ID_COLS].agg(''.join, axis=1)

    return df


def read_puf(path, skip_bad=False):
    """
    read a raw puf csv.

    skip_bad tolerates malformed lines instead of raising, for the rare source file with
    corrupt records (Isabela's MEMBERS csv has two spliced rows around line 763k). the
    skipped count is always printed - a silently shortened file would be worse than a crash.
    """
    if not skip_bad:
        return pd.read_csv(path, dtype=ID_DTYPES)

    df = pd.read_csv(path, dtype=ID_DTYPES, on_bad_lines='skip')

    # puf files carry no quoted fields, so raw lines map 1:1 onto records.
    with open(path, encoding='utf-8', errors='replace') as fh:
        raw = sum(1 for _ in fh) - 1

    if raw != len(df):
        print(f"  WARNING {os.path.basename(path)}: skipped {raw - len(df)} malformed line(s)")

    return df


def load_household(path, skip_bad=False):
    """load and clean the HOUSEHOLD puf file. psgc key is built before the numeric coercion."""
    hh = read_puf(path, skip_bad)
    hh = make_psgc(hh)

    # reformat into integers
    # replace empty or whitespace-only strings with NaN
    hh = hh.replace(r'^\s*$', np.nan, regex=True)
    # convert every column to nullable integer dtype (non-numeric -> NaN -> <NA>).
    # note this also turns psgc2021 into the integer n_id.
    for col in hh.columns:
        hh[col] = pd.to_numeric(hh[col], errors='coerce').astype('Int64')

    # remove the non vacant na values are 'homeless' (code 600000) or otherwise poorly-defined
    # households. net effect of these two steps is 'drop any row with a NaN, drop HSN 999999';
    # kept in two parts to stay diffable against the source notebook.
    mask_keep = (hh['HSN'] == HSN_DROP) | (~hh.isna().any(axis=1))
    hh = hh.loc[mask_keep].copy()
    hh = hh.loc[hh['HSN'] != HSN_DROP]

    return hh


def load_members(path, skip_bad=False):
    """load the MEMBERS puf file and count population per household."""
    mem = read_puf(path, skip_bad)
    mem = make_psgc(mem)

    pop = mem.groupby(['psgc2021', 'HSN'])['LNA'].count().reset_index()
    pop['psgc2021'] = pop['psgc2021'].astype(int)

    return pop


###############
### MAPPING ###
def map_household(hh, valuesets):
    """replace census codes with informative values and rename to the neighbourhoods schema."""
    # for building id, use HSN. some buildings share wall/plot so are the same housing
    # unit but multi-family.
    sub = hh.loc[:, list(COL_RENAME.keys()) + ['psgc2021', 'HUSN', 'HSN']].copy()

    # htype
    sub['B1'] = sub['B1'].map(B1_MAP).map(RASMI_TO_RECC)
    # replace floor area code with band average
    sub['D1'] = sub['D1'].map(D1_MEAN)
    # replace year built with age cohort
    sub['B8'] = sub['B8'].map(B8_MAP)

    # the remaining columns take their labels from the metadata
    for col in LABEL_COLS:
        sub[col] = sub[col].map(valuesets[col])

    return sub


def report_unmapped(raw, mapped, name):
    """warn about census codes that mapped to NaN, so they aren't lost silently."""
    checked = ['B1', 'D1', 'B8'] + LABEL_COLS

    for col in checked:
        lost = mapped[col].isna() & raw[col].notna()
        if not lost.any():
            continue

        counts = raw.loc[lost, col].value_counts().sort_index()
        for code, n in counts.items():
            print(f"  WARNING {name}: {col} ({COL_RENAME[col]}) code {code} "
                  f"has no mapped value, {n} rows -> NaN")


##################
### ASSEMBLING ###
def build_dataset(cfg, ds, valuesets):
    """build the neighbourhoods rows for one city dataset."""
    skip_bad = cfg.get('skip_bad_lines', False)
    hh = load_household(resolve_data(cfg, ds['household']), skip_bad)
    pop = load_members(resolve_data(cfg, ds['members']), skip_bad)

    mapped = map_household(hh, valuesets)
    report_unmapped(hh, mapped, ds['name'])

    # optionally fill unmapped codes rather than leaving them NaN
    fill = cfg.get('unmapped_label')
    if fill:
        for col in ['B1'] + LABEL_COLS:
            mapped[col] = mapped[col].fillna(fill)

    # append household population
    out = pd.merge(mapped, pop, on=['psgc2021', 'HSN'], how='left')

    # a household with no member records has no population, so it can't carry an m2-per-person
    # figure - drop it rather than let a NaN pop reach the sampler. this is a no-op on every
    # intact dataset; it only bites where corrupt MEMBERS rows orphaned a household.
    orphans = out['LNA'].isna()
    if orphans.any():
        print(f"  WARNING {ds['name']}: {int(orphans.sum())} household(s) have no member "
              f"records, dropped")
        out = out.loc[~orphans].copy()

    # rename to the neighbourhoods schema
    out = out.rename(columns=COL_RENAME).rename(columns={'LNA': 'pop', 'psgc2021': 'n_id'})

    # in_city marks the city of interest (1) vs sample-space expansion (0).
    out['in_city'] = ds.get('in_city', 1)

    cols = list(OUT_COLS)
    if cfg.get('add_source_col'):
        out['source'] = ds['name']
        cols.append('source')

    return out[cols]


def build_neighbourhoods(cfg):
    """build the full neighbourhoods table across every configured dataset."""
    valuesets = load_valuesets(cfg)

    # each city is processed separately before concatenating: HSN is only unique
    # within a barangay, so the population merge has to happen per dataset.
    frames = []
    for ds in cfg['datasets']:
        print(f"  reading {ds['name']}...")
        frames.append(build_dataset(cfg, ds, valuesets))

    return pd.concat(frames, ignore_index=True)


def report(nb):
    """print sanity checks on the assembled table."""
    print(f"  rows: {len(nb)}, neighbourhoods (n_id): {nb['n_id'].nunique()}")
    print(f"  census population: {int(nb['pop'].sum())}")

    print(f"  htype: {nb['htype'].value_counts().to_dict()}")

    nulls = nb.isna().sum()
    nulls = nulls.loc[nulls > 0]
    if len(nulls):
        print(f"  nulls: {nulls.to_dict()}")

    m2_per = (nb['m2'] / nb['pop']).describe()
    print(f"  m2 per person: mean {m2_per['mean']:.4f}, "
          f"median {m2_per['50%']:.4f}, max {m2_per['max']:.4f}")


###########
### CLI ###
def resolve_data(cfg, rel_path):
    """resolve a raw census path against data_root. raw data lives outside the repo."""
    root = cfg.get('data_root', '')
    if os.path.isabs(root):
        return os.path.join(root, rel_path)

    return os.path.join(_REPO_ROOT, root, rel_path)


def find_configs(args):
    """get ingest configs to run: cli args, else every ingest_*.yaml next to this script."""
    if args:
        return args

    found = sorted(glob.glob(_THIS_DIR + "ingest_*.yaml"))
    return [os.path.basename(f) for f in found]


def run_config(config_file, force=False):
    """run the full ingest for a single config file."""
    with open(_THIS_DIR + config_file, 'r') as stream:
        cfg = dict(yaml.load(stream, Loader=yaml.Loader))

    out_path = Config.input_files + cfg['output']
    print(f"  target {out_path}")

    if os.path.exists(out_path) and not force:
        raise FileExistsError(f"{out_path} exists, pass --force to overwrite")

    nb = build_neighbourhoods(cfg)
    report(nb)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    nb.to_csv(out_path, index=False)

    return out_path


def main(args):
    force = '--force' in args
    args = [a for a in args if a != '--force']

    configs = find_configs(args)
    if not configs:
        print("no ingest_*.yaml found in " + _THIS_DIR)
        return 1

    failed = {}
    for config_file in configs:
        print(f"ingesting {config_file}...")
        try:
            print(f"  wrote {run_config(config_file, force)}")
        except Exception as e:
            # keep going so one bad config doesn't sink the batch.
            failed[config_file] = e
            print(f"  FAILED: {e}")

    print(f"\n{len(configs) - len(failed)}/{len(configs)} configs completed.")
    for config_file, e in failed.items():
        print(f"  {config_file}: {e}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
