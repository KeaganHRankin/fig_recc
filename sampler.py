"""
Class for city-level FIG-RECC sampling.
Written by Keagan H. Rankin 2026 IRP project
"""

import numpy as np
import scipy as sp
import pandas as pd
from tqdm import tqdm


class FIGRECCSampler:
    """
    a sampler that performs fig-like subsetting
    and sampling on neighbourhoods given some scenario config.
    Methods help find subset of neighbourhoods which meeting scenario
    conditions. Other methods store and return information about those
    neighbourhoods + inputs for RECC.
    """
    def __init__(self, config_obj):
        # store some vars from passed config object
        self.config = config_obj

        self.n_df = self.config.neighbourhoods.copy()
        self.n_df['m2_per_'] = self.n_df['m2']/self.n_df['pop']

        self.m2 = self.config.m2_per_p.copy()

        self.base_year = self.config.params['base_year']
        #self.pop_df = self.config.population.copy()

        # random seed if needed
        self.rng_seed = 42



    ###############################
    ### SAMPLE LIMITING METHODS ###
    def limit_arbitrary(self, col, limit, extr='min', collator='first'):
        """
        get neighbourhoods that don't meet some limiting
        arbitrary neighbourhood property.
        """
        ns_x = self.n_df.groupby('n_id')[col].agg(collator)

        if extr == 'min':
            ns_diff = ns_x.loc[ns_x<limit]
        if extr == 'max':
            ns_diff = ns_x.loc[ns_x>limit]
        return ns_diff.index.to_list()


    def limit_m2(self, limit, extr='min'):
        """get neighbourhoods below some avg m2 per person."""
        ns_m2 = self.n_df.groupby('n_id')['m2_per_'].mean()

        if extr == 'min':
            ns_diff = ns_m2.loc[ns_m2<limit]
        if extr == 'max':
            ns_diff = ns_m2.loc[ns_m2>limit]
        return ns_diff.index.to_list()


    def limit_htype(self, limit, htype, extr='min'):
        """get neighbourhoods exceeding min/max of some housing type."""
        ns_type = self.n_df.groupby('n_id')['htype'].value_counts(normalize=True)
        ns_type = ns_type.unstack()

        # get neighbourhoods which exceed the imposed constraint (set difference).
        if extr == 'min':
            ns_diff = ns_type.loc[ns_type[htype]<limit]
        if extr == 'max':
            ns_diff = ns_type.loc[ns_type[htype]>limit]
        return ns_diff.index.to_list()


    def get_limited_htype(self, ns):
        """limit neighbourhood sample based on config params."""

        # apply typesplit limits
        if "min_sfh_share" in self.config.params['constraints']:
            d = self.limit_htype(self.config.params['constraints']['min_sfh_share'], 'sfh', 'min')
            ns = np.setdiff1d(ns, d) # set diff returns ns not in d
        
        if "min_mfh_share" in self.config.params['constraints']:
            d = self.limit_htype(self.config.params['constraints']['min_mfh_share'], 'mfh', 'min')
            ns = np.setdiff1d(ns, d)

        if "max_sfh_share" in self.config.params['constraints']:
            d = self.limit_htype(self.config.params['constraints']['max_sfh_share'], 'sfh', 'max')
            ns = np.setdiff1d(ns, d)

        if "max_mfh_share" in self.config.params['constraints']:
            d = self.limit_htype(self.config.params['constraints']['max_sfh_share'], 'mfh', 'max')
            ns = np.setdiff1d(ns, d)

        return ns
    
        
    def get_subset_period(self, period):
        """get limited neighbourhood sample for the given period."""
        # start by getting all neighbourhoods
        ns = self.n_df['n_id'].unique()

        # get the neighbourhoods that meet avg m2 sufficiency for period.
        m2_lim = self.m2.loc[self.m2['period'] == period, 'res'].squeeze()
        d = self.limit_m2(m2_lim)
        ns = np.setdiff1d(ns, d)

        # get neighbourhoods meeting htype condition
        ns = self.get_limited_htype(ns)

        # get neighbourhoods meeting arbitrary conditions
        for k, v in self.config.params['constraints'].items():
            if k not in self.config.constraint_bline:
                dx = self.limit_arbitrary(col=v['col'], 
                                          limit=v['limit'], 
                                          extr=v['extrema'],
                                          collator=v['collator'])
                
                ns = np.setdiff1d(ns, dx)

        # check before returing
        if len(ns) <= 0:
            raise ValueError("no neighbourhoods meet conditions, empty list cannot be sampled.")

        return ns


    def get_subset_all_periods(self):
        """for all periods in params, get the neighbourhood subset."""
        self.n_subset = {}

        # store subset n_ids for all 
        for p in self.config.params['model_periods']:
            self.n_subset[p] = self.get_subset_period(p)



    ##############################
    ### SAMPLE SUMMARY METHODS ###
    # these methods are run after getting the subset `get_subset_all_periods()`.
    def get_res_current_stock(self):
        """return summary of current stock and age using in_city parameter."""
        # get neighbourhoods in city of interest.
        if 'in_city' not in self.n_df.columns.to_list():
            return ValueError('neighbourhood input requires "in_city" column.')
        
        in_c = self.n_df.loc[self.n_df['in_city'] == 1]

        # get and return age cohorts
        return in_c.groupby('age_cohort')['htype'].value_counts().reset_index()


    def get_res_typesplit(self):
        """return type split of limited sample."""
        ts = {}
        # for each period
        for k, v in self.n_subset.items():
            # get constrained sample
            n_df_sub = self.n_df.loc[self.n_df['n_id'].isin(v)]
            # store the typesplit of constrained sample
            ts[k] = n_df_sub['htype'].value_counts(normalize=True).round(2).to_dict()

        return ts
    

    def get_x_split(self, xarg):
        """return split of limited sample for any arbitrary argument."""
        ts = {}
        # for each period
        for k, v in self.n_subset.items():
            # get constrained sample
            n_df_sub = self.n_df.loc[self.n_df['n_id'].isin(v)]
            # store the typesplit of constrained sample
            ts[k] = n_df_sub[xarg].value_counts(normalize=True).to_dict()

        return ts


    def output_to_recc(self):
        """output relevant scenario details to RECC with appropriate names."""
        ## residential
        recc_resvars = ['2_S_RECC_FinalProducts_2015_resbuildings_Cities_V1.0.csv',
                        '2_S_RECC_FinalProducts_Future_resbuildings_Cities_V1.0.csv',
                        '3_SHA_TypeSplit_Buildings.csv']
        # stock
        self.get_res_current_stock().to_csv(self.config.cache_dir+recc_resvars[0])
        # m2
        self.m2[['period','res']].to_csv(self.config.cache_dir+recc_resvars[1])
        # typesplit
        pd.DataFrame(self.get_res_typesplit()).T.to_csv(self.config.cache_dir+recc_resvars[2])

        # user-specified extra splits
        self.output_extra_splits()


    def output_extra_splits(self):
        """output any user-configured extra column splits (see params.yaml: extra_splits)."""
        for col in self.config.params.get('extra_splits', []):
            pd.DataFrame(self.get_x_split(col)).T.to_csv(f"{self.config.cache_dir}{col}_split.csv")


    ###############################
    ### RANDOM SAMPLING METHODS ###
    def counter(self, sample, period, need_cond='m2'):
        """check halt based on need condition."""
        self.period_pop = self.pop_df[self.pop_df['period'] == period, 'pop'].squeeze()
        return None
    

    def random_sample_n(self, n_ids, n=1):
        """sample n neighbourhoods given some ids."""
        
        # sample some number of neighbourhoods
        rng = np.random.default_rng(self.rng_seed)
        sampled_n_ids = rng.choice(n_ids, n, replace=True)
        
        # store partitioned neighbourhoods
        groups = {k: g for k, g in self.n_df.groupby("n_id")}
        samples = [groups.get(sid) for sid in sampled_n_ids]

        return pd.concat(samples)