"""
Sets up configuration for city-level FIG-RECC sampling
Written by Keagan H. Rankin 2026 IRP project
"""

import os
import pandas as pd
import yaml


class Config:
    """object that imports and stores setup for one FIG-RECC scenario."""
    # File locations
    _this_dir = os.path.realpath(os.path.dirname(__file__)) + "/"
    input_files = _this_dir + 'input_files/'
    cache_root = _this_dir + "data_cache/"

    # base_list of constraints handled by dedicated sampler logic
    constraint_bline = ['need_cond','min_sfh_share','min_mfh_share','max_sfh_share','max_mfh_share']


    def __init__(self, params_file="params.yaml"):
        self.params_file = params_file

        # run setup
        self._get_params()
        self._setup_cache()


    def _get_params(self):
        """get parameters from yaml and other input files."""
        # get yaml global params
        with open(self.input_files + self.params_file, 'r') as stream:
            self.params = dict(yaml.load(stream, Loader=yaml.Loader))

        # scenario name for output folder, defaults to the params filename stem.
        self.scenario = self.params.get('scenario_name',
                                        os.path.splitext(self.params_file)[0])

        # get other variables
        self.m2_per_p = pd.read_csv(self.input_files + self.params['param_files']['folder'] + '/' + self.params['param_files']['m2_per_p'])
        self.neighbourhoods = pd.read_csv(self.input_files + self.params['param_files']['folder'] + '/' + self.params['param_files']['neighbourhoods'])
        self.population = pd.read_csv(self.input_files + self.params['param_files']['folder'] + '/' + self.params['param_files']['pop'])


    def _setup_cache(self):
        """create this scenario's output folder. trailing / - output paths are concatenated."""
        self.cache_dir = self.cache_root + self.scenario + "/"
        os.makedirs(self.cache_dir, exist_ok=True)
