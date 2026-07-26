"""
Entry point for FIG-RECC sampling.
Written by Keagan H. Rankin 2026 IRP project
"""

from config import Config
from sampler import FIGRECCSampler


def main():
    config = Config()
    sampler = FIGRECCSampler(config)
    sampler.get_subset_all_periods()
    sampler.output_to_recc()


if __name__ == "__main__":
    main()
