"""
Sets up configuration for city-level FIG-RECC sampling
Written by Keagan H. Rankin 2026 IRP project
"""

import os
import pandas as pd
import yaml


class Config:
    """object that imports and stores setup for FIG-RECC."""
    # File locations
    _this_dir = os.path.realpath(os.path.dirname(__file__)) + "/"
    input_files = _this_dir + 'input_files/'
    cache_dir = _this_dir + "data_cache/"
    if not os.path.exists(cache_dir): os.mkdir(cache_dir)

    # singleton pattern - only once instance.
    _instance = None 

    def __new__(cls, *args, **kwargs):
        if isinstance(cls._instance, cls): return cls._instance
        cls._instance = super(Config, cls).__new__(cls, *args, **kwargs) 
        
        # run setup
        cls._get_params(cls._instance)

        return cls._instance


    def _get_params(cls):
        """get parameters from yaml and other input files."""
        # get yaml global params
        stream = open(Config.input_files + "params.yaml", 'r')
        Config.params = dict(yaml.load(stream, Loader=yaml.Loader))

        # get other variables
        Config.m2_per_p = pd.read_csv(Config.input_files + Config.params['m2_per_p'])
        Config.neighbourhoods = pd.read_csv(Config.input_files + Config.params['neighbourhoods'])
        Config.population = pd.read_csv(Config.input_files + Config.params['pop'])

        # get base_list of constraints
        Config.constraint_bline = ['need_cond','min_sfh_share','min_mfh_share','max_sfh_share','max_mfh_share']
