# coding: utf-8

"""
Configuration of the tt_semileptonic analysis.
"""

import law
import order as od
import tt_semileptonic.config.datasets_helper as datasets_helper
import tt_semileptonic.config.run3.config_helper as config_helper


#
# the main analysis object
#

analysis_tt_semileptonic = ana = od.Analysis(
    name="analysis_tt_semileptonic",
    id=1,
)

# analysis-global versions
# (see config.x.versions below for more info)
ana.x.versions = {}

# files of bash sandboxes that might be required by remote tasks
# (used in cf.HTCondorWorkflow)
ana.x.bash_sandboxes = ["$CF_BASE/sandboxes/cf.sh"]
default_sandbox = law.Sandbox.new(law.config.get("analysis", "default_columnar_sandbox"))
if default_sandbox.sandbox_type == "bash" and default_sandbox.name not in ana.x.bash_sandboxes:
    ana.x.bash_sandboxes.append(default_sandbox.name)

# files of cmssw sandboxes that might be required by remote tasks
# (used in cf.HTCondorWorkflow)
ana.x.cmssw_sandboxes = [
    "$CF_BASE/sandboxes/cmssw_default.sh",
]

# config groups for conveniently looping over certain configs
# (used in wrapper_factory)
ana.x.config_groups = {}

# named function hooks that can modify store_parts of task outputs if needed
ana.x.store_parts_modifiers = {}

# histogramming hooks, invoked before creating plots when --hist-hook parameter set
ana.x.hist_hooks = {}


#
# setup configs
#


# an example config is setup below, based on cms NanoAOD v9 for Run2 2017, focussing on
# ttbar and single top MCs, plus single muon data
# update this config or add additional ones to accomodate the needs of your analysis

from cmsdb.campaigns.run3_2024_nano_v15 import campaign_run3_2024_nano_v15 as campaign_run3_2024_nano_v15

config_2024 = config_helper.create_new_config(
    ana,
    campaign_run3_2024_nano_v15.copy(),
    config_name="run3_tt_semileptonic_2024_nano_v15",
    config_id=3_24_11
)

config_2024_small = config_helper.create_new_config(
    ana,
    campaign_run3_2024_nano_v15.copy(),
    config_name="run3_tt_semileptonic_2024_nano_v15_small",
    config_id=3_24_21,
    limit_dataset_files=2
)