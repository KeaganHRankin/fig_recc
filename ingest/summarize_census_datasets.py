"""
Scan the raw PSA CPH PUF census drive and regenerate ingest/census_datasets.yaml.
Written by Keagan H. Rankin 2026 IRP project

The census drive is only partly populated - many dataset folders exist but hold empty or
missing csvs. This records which ones are actually usable so ingest configs can be written
against real data. Re-run it whenever the drive contents change.

    python ingest/summarize_census_datasets.py            # scan DEFAULT_ROOT, rewrite the yaml
    python ingest/summarize_census_datasets.py <root>     # scan a different drive/path
    python ingest/summarize_census_datasets.py --check    # report drift, write nothing
"""

import os
import sys

# default census drive root. override with a positional arg if the drive letter changes.
DEFAULT_ROOT = "D:/PH_2020_census/PUF for CPH Form 2 (Common Household Questionnaire)/"

_THIS_DIR = os.path.realpath(os.path.dirname(__file__)) + "/"
OUT_FILE = _THIS_DIR + "census_datasets.yaml"

# top-level folders that are documentation, not census regions.
SKIP_DIRS = ["File Description and Annexes", "Questionnaires"]

# a dataset needs both halves: households carry building attributes, members the population
# count that gets merged onto them.
PARTS = ["HOUSEHOLD", "MEMBERS"]

# the filename convention the PUF files mostly follow. departures from it are real and are
# called out in the generated header, since a config composed from the folder name would fail.
NAME_TEMPLATE = "CPH PUF 2020 {name} - {part}.CSV"


####################
### DRIVE SCAN ###
def find_part(files, part):
    """find the HOUSEHOLD or MEMBERS csv among a dataset folder's files."""
    hits = [f for f in files if part in f.upper() and f.upper().endswith(".CSV")]
    return sorted(hits)[0] if hits else None


def classify(dir_path):
    """
    inspect one dataset folder and return (files_by_part, problems).

    an empty problems list means the dataset is usable.
    """
    try:
        files = [f for f in os.listdir(dir_path) if os.path.isfile(dir_path + "/" + f)]
    except OSError as e:
        return {}, [f"unreadable ({e.strerror})"]

    if not files:
        return {}, ["no files present"]

    found, problems = {}, []
    for part in PARTS:
        name = find_part(files, part)
        if name is None:
            problems.append(f"{part} csv absent")
            continue

        found[part] = name
        if os.path.getsize(dir_path + "/" + name) == 0:
            problems.append(f"{part} csv is 0 bytes")

    return found, problems


def scan(root):
    """walk the census root and split its dataset folders into available/unavailable."""
    available, unavailable = [], []

    for region in sorted(os.listdir(root)):
        region_path = root + region
        if region in SKIP_DIRS or not os.path.isdir(region_path):
            continue

        for dataset in sorted(os.listdir(region_path)):
            dir_path = region_path + "/" + dataset
            if not os.path.isdir(dir_path):
                continue

            found, problems = classify(dir_path)
            if problems:
                unavailable.append({'name': dataset, 'region': region,
                                    'reason': "; ".join(problems)})
                continue

            available.append({
                'name': dataset,
                'region': region,
                'dir': f"{region}/{dataset}",
                'household': found['HOUSEHOLD'],
                'members': found['MEMBERS'],
                'size_mb': {p: round(os.path.getsize(dir_path + "/" + found[p]) / 1024 ** 2, 1)
                            for p in PARTS},
            })

    return available, unavailable


def find_irregular(available):
    """find datasets whose filenames don't follow NAME_TEMPLATE, so they can't be composed."""
    odd = []
    for d in available:
        for part, key in zip(PARTS, ['household', 'members']):
            if d[key] != NAME_TEMPLATE.format(name=d['name'], part=part):
                odd.append(f"{d['name']}/{part} -> {d[key]}")

    return odd


##################
### RENDERING ###
def q(s):
    """yaml-quote a string."""
    return '"' + str(s).replace('"', '\\"') + '"'


def group_by_region(rows):
    """group scanned rows by region, preserving the sorted scan order."""
    out = {}
    for r in rows:
        out.setdefault(r['region'], []).append(r)

    return out


def render(available, unavailable, root):
    """build the census_datasets.yaml text."""
    L = [
        "# Census datasets available on the external drive",
        "# GENERATED FILE - do not hand-edit. Regenerate with:",
        "#   python ingest/summarize_census_datasets.py",
        "#",
        "# A dataset is 'available' only when BOTH its HOUSEHOLD and MEMBERS csv are present and",
        "# non-empty - ph_census_ingest.py needs the pair (households give building attributes,",
        "# members give the population count merged onto them).",
        "#",
        "# Paths under `dir` are relative to the ingest config's data_root, i.e.",
        f"#   data_root: {q(root)}",
        "# so a dataset entry in an ingest config is:",
        "#   - name: mandaue_city",
        '#     household: "<dir>/<household>"',
        '#     members: "<dir>/<members>"',
        "#     in_city: 0",
    ]

    odd = find_irregular(available)
    if odd:
        L += [
            "#",
            "# NOTE these filenames do NOT follow the usual",
            f"#   {NAME_TEMPLATE.format(name='<name>', part='<part>')}",
            "# convention, so they cannot be composed from the folder name - copy them exactly:",
        ] + [f"#   {o}" for o in odd]

    L += [
        "",
        "summary:",
        f"  available: {len(available)}",
        f"  unavailable: {len(unavailable)}",
        f"  total: {len(available) + len(unavailable)}",
        "",
        "## Usable datasets, grouped by region",
        "available:",
    ]

    for region, rows in group_by_region(available).items():
        L.append(f"  # {region} ({len(rows)})")
        for r in rows:
            L += [
                f"  - name: {q(r['name'])}",
                f"    region: {q(region)}",
                f"    dir: {q(r['dir'])}",
                f"    household: {q(r['household'])}",
                f"    members: {q(r['members'])}",
                f"    size_mb: {{household: {r['size_mb']['HOUSEHOLD']}, "
                f"members: {r['size_mb']['MEMBERS']}}}",
            ]
        L.append("")

    L += [
        "## Datasets present as folders but with no usable data.",
        "## Listed so a re-download can target them; do not reference these from an ingest config.",
        "unavailable:",
    ]

    for region, rows in group_by_region(unavailable).items():
        reasons = sorted({r['reason'] for r in rows})
        L.append(f"  # {region} ({len(rows)}) - {'; '.join(reasons)}")
        for r in rows:
            L += [
                f"  - name: {q(r['name'])}",
                f"    region: {q(region)}",
                f"    reason: {q(r['reason'])}",
            ]
        L.append("")

    return "\n".join(L).rstrip() + "\n"


###########
### CLI ###
def main(args):
    check = '--check' in args
    args = [a for a in args if a != '--check']

    root = args[0] if args else DEFAULT_ROOT
    root = root.replace("\\", "/").rstrip("/") + "/"

    if not os.path.isdir(root):
        print(f"census root not found: {root}")
        return 1

    print(f"scanning {root}...")
    available, unavailable = scan(root)

    if not available and not unavailable:
        print("  no dataset folders found - is this the right root?")
        return 1

    for region, rows in group_by_region(available).items():
        print(f"  {region}: {len(rows)} available")
    print(f"  {len(available)} available / {len(unavailable)} unavailable "
          f"({len(available) + len(unavailable)} total)")

    for o in find_irregular(available):
        print(f"  NOTE irregular filename: {o}")

    text = render(available, unavailable, root)
    current = open(OUT_FILE, encoding='utf-8').read() if os.path.exists(OUT_FILE) else None

    if check:
        if text == current:
            print(f"  {OUT_FILE} is up to date")
            return 0

        print(f"  {OUT_FILE} is STALE - re-run without --check to update")
        return 1

    if text == current:
        print(f"  no change to {OUT_FILE}")
        return 0

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"  wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
