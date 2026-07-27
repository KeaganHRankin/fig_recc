"""
Entry point for FIG-RECC sampling.
Written by Keagan H. Rankin 2026 IRP project
"""

import glob
import os
import sys

from config import Config
from sampler import FIGRECCSampler


def find_scenarios(args):
    """get params files to run: cli args, else every params*.yaml in input_files."""
    if args:
        return args

    found = sorted(glob.glob(Config.input_files + "params*.yaml"))
    return [os.path.basename(f) for f in found]


def run_scenario(params_file):
    """run the full pipeline for a single params file."""
    config = Config(params_file)
    sampler = FIGRECCSampler(config)
    sampler.get_subset_all_periods()
    sampler.output_to_recc()

    return config.cache_dir


def main(args):
    scenarios = find_scenarios(args)
    if not scenarios:
        print("no params*.yaml found in " + Config.input_files)
        return 1

    failed = {}
    for params_file in scenarios:
        print(f"running {params_file}...")
        try:
            print(f"  wrote {run_scenario(params_file)}")
        except Exception as e:
            # keep going so one over-constrained scenario doesn't sink the batch.
            failed[params_file] = e
            print(f"  FAILED: {e}")

    print(f"\n{len(scenarios) - len(failed)}/{len(scenarios)} scenarios completed.")
    for params_file, e in failed.items():
        print(f"  {params_file}: {e}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
