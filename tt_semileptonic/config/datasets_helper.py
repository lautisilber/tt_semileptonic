# coding: utf-8

"""
Configuration of datasets for the tt_semileptonic analysis configuration
"""

from __future__ import annotations
import itertools
import order as od
import law

logger = law.logger.get_logger(__name__)

def _config_add_dataset(config: od.Config, dataset_name: str) -> od.Dataset:
    try:
        ds = config.add_dataset(config.campaign.get_dataset(dataset_name))
        return ds
    except ValueError as err:
        logger.error(f"Couldn't find dataset name '{dataset_name}' in config '{config.name}' with campaign '{config.campaign.name}'.\nAvailable dataset names:\n[{', '.join(d.name for d in config.campaign.datasets)}]")
        
        q = __import__('functools').partial(__import__('os')._exit, 0)
        __import__('IPython').embed()

        raise err

def add_data_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds data datasets to the config based on the run number and campaign tag.
    """
    if config.campaign.x.run == 2:
        config.x.data_streams = [
            "mu",
            "e",
            "pho",
        ]
    elif config.campaign.x.run == 3:
        config.x.data_streams = [
            "mu",
            # "egamma",
            "e", # 'egamma' was deprecated in facour of 'e'
        ]
    else:
        raise ValueError(f"Unsupported run number: {config.campaign.x.run}")

    data_eras = {
        "2017": list("cdef"),
        "2022preEE": list("cd"),
        "2022postEE": list("efg"),
        "2023preBPix": ["c1", "c2", "c3", "c4"],
        "2023postBPix": ["d1", "d2"],
        "2024": list("cdefghi"),
    }[config.x.cpn_tag]

    data_datasets = [
        f"data_{stream}_{era}"
        for era in data_eras
        for stream in config.x.data_streams
    ]

    for dataset in data_datasets:
        # ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds = _config_add_dataset(config, dataset)
        ds.add_tag("is_data")

        if ds.name.startswith("data_mu"):
            ds.add_tag("is_mu_data")
        if ds.name.startswith("data_e"):
            ds.add_tag({"is_e_data", "is_egamma_data"})
        if ds.name.startswith("data_pho"):
            ds.add_tag({"is_pho_data", "is_egamma_data"})

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)
    
    if log:
        logger.info(f"Added {len(data_datasets)} data datasets.")

def add_dy_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds DY+jets datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag

    datasets = {
        2: {
            "2017": [
                "dy_m50toinf_ht70to100_madgraph",
                "dy_m50toinf_ht100to200_madgraph",
                "dy_m50toinf_ht200to400_madgraph",
                "dy_m50toinf_ht400to600_madgraph",
                "dy_m50toinf_ht600to800_madgraph",
                "dy_m50toinf_ht800to1200_madgraph",
                "dy_m50toinf_ht1200to2500_madgraph",
                "dy_m50toinf_ht2500toinf_madgraph",
            ],
        },
        3: {
            "2022preEE": [
                "dy_m4to50_ht40to70_madgraph",
                "dy_m4to50_ht70to100_madgraph",
                "dy_m4to50_ht100to400_madgraph",
                "dy_m4to50_ht400to800_madgraph",
                "dy_m4to50_ht800to1500_madgraph",
                "dy_m4to50_ht1500to2500_madgraph",
                "dy_m4to50_ht2500toinf_madgraph",
                "dy_m50to120_ht40to70_madgraph",
                "dy_m50to120_ht70to100_madgraph",
                "dy_m50to120_ht100to400_madgraph",
                "dy_m50to120_ht400to800_madgraph",
            ],
            "2022postEE": [  # Same as preEE
                "dy_m4to50_ht40to70_madgraph",   # FIXME AssertionError (lim. stat.)
                "dy_m4to50_ht70to100_madgraph",
                "dy_m4to50_ht100to400_madgraph",  # FIXME AssertionError (lim. stat.)
                "dy_m4to50_ht400to800_madgraph",
                "dy_m4to50_ht800to1500_madgraph",
                "dy_m4to50_ht1500to2500_madgraph",
                "dy_m4to50_ht2500toinf_madgraph",
                "dy_m50to120_ht40to70_madgraph",
                "dy_m50to120_ht70to100_madgraph",
                "dy_m50to120_ht100to400_madgraph",
                "dy_m50to120_ht400to800_madgraph",
            ],
            "2024": [
                # no HT-binned samples available yet, but in production chain -> to be checked!
                # https://cms-pdmv-prod.web.cern.ch/grasp/samples?campaign=RunIII2024Summer24*GS&dataset=DYto2*-4J # noqa
                # using LO samples binned in lepton flavor
                # "dy_4j_mumu_m50toinf_madgraph",
                # "dy_4j_ee_m50toinf_madgraph",
                # "dy_4j_tautau_m50toinf_madgraph",

                "dy_ee_m50toinf_amcatnlo",
                # "dy_ee_m50toinf_0j_amcatnlo",
                # "dy_ee_m50toinf_1j_amcatnlo",
                # "dy_ee_m50toinf_2j_amcatnlo",

                "dy_mumu_m50toinf_amcatnlo",
                # "dy_mumu_m50toinf_0j_amcatnlo",
                # "dy_mumu_m50toinf_1j_amcatnlo",
                # "dy_mumu_m50toinf_2j_amcatnlo",
            ],
        },
    }

    try:
        datasets_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"DY - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in datasets_list:
        ds = _config_add_dataset(config, dataset)
        ds.add_tag({"is_dy", "is_v_jets", "is_z_jets"})

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(datasets_list)} DY datasets.")

def add_w_lnu_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds W+jets datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag

    datasets = {
        2: {
            "2017": [
                "w_lnu_ht70to100_madgraph",
                "w_lnu_ht100to200_madgraph",
                "w_lnu_ht200to400_madgraph",
                "w_lnu_ht400to600_madgraph",
                "w_lnu_ht600to800_madgraph",
                "w_lnu_ht800to1200_madgraph",
                "w_lnu_ht1200to2500_madgraph",
                "w_lnu_ht2500toinf_madgraph",
            ],
        },
        3: {
            "2022preEE": [
                "w_lnu_mlnu0to120_ht40to100_madgraph",
                "w_lnu_mlnu0to120_ht100to400_madgraph",
                "w_lnu_mlnu0to120_ht400to800_madgraph",
                "w_lnu_mlnu0to120_ht800to1500_madgraph",
                "w_lnu_mlnu0to120_ht1500to2500_madgraph",
                "w_lnu_mlnu0to120_ht2500toinf_madgraph",
            ],
            "2022postEE": [  # Same as preEE
                "w_lnu_mlnu0to120_ht40to100_madgraph",
                "w_lnu_mlnu0to120_ht100to400_madgraph",
                "w_lnu_mlnu0to120_ht400to800_madgraph",
                "w_lnu_mlnu0to120_ht800to1500_madgraph",
                "w_lnu_mlnu0to120_ht1500to2500_madgraph",
                "w_lnu_mlnu0to120_ht2500toinf_madgraph",
            ],
            "2024": [
                # no HT-binned samples available yet, but in production chain -> to be checked!
                # https://cms-pdmv-prod.web.cern.ch/grasp/samples?campaign=RunIII2024Summer24*GS&dataset=WtoLNu-4Jets_Bin-HT  # noqa
                # # NLO samples: have very little stats in our phasespace -> use LO samples
                # "w_lnu_1j_pt40to100_amcatnlo",
                # "w_lnu_1j_pt100to200_amcatnlo",
                # "w_lnu_1j_pt200to400_amcatnlo",
                # "w_lnu_1j_pt400to600_amcatnlo",
                # "w_lnu_1j_pt600toinf_amcatnlo",
                # "w_lnu_2j_pt40to100_amcatnlo",
                # "w_lnu_2j_pt100to200_amcatnlo",
                # "w_lnu_2j_pt200to400_amcatnlo",
                # "w_lnu_2j_pt400to600_amcatnlo",
                # "w_lnu_2j_pt600toinf_amcatnlo",
                # LO samples binned in jet multiplicity only
                "w_lnu_1j_madgraph",
                "w_lnu_2j_madgraph",
                "w_lnu_3j_madgraph",
                "w_lnu_4j_madgraph",
            ],
        },
    }
    try:
        datasets_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"W+jets - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in datasets_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag({"is_w_lnu", "is_v_jets", "is_w_jets"})

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(datasets_list)} W+jets datasets.")

def add_vv_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds diboson datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag
    diboson_names = [
        "ww_pythia",
        "wz_pythia",
        "zz_pythia",
    ]
    datasets = {
        2: {
            "2017": diboson_names,
        },
        3: {
            "2022preEE": diboson_names,
            "2022postEE": diboson_names,
            "2023preBPix": diboson_names,
            "2023postBPix": diboson_names,
            "2024": diboson_names,
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"Diboson - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag({"is_vv", "is_diboson"})

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} diboson datasets.")

def add_tt_sl_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds ttbar_sl datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag
    tt_names = [
        "tt_sl_powheg",
    ]
    datasets = {
        2: {
            "2017": tt_names,
        },
        3: {
            "2022preEE": tt_names,
            "2022postEE": tt_names,
            "2023preBPix": tt_names,
            "2023postBPix": tt_names,
            "2024": tt_names,
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"TTbar - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag({"has_top", "has_ttbar", "is_sm_ttbar"})
        if ds.name.startswith("tt_sl"):
            ds.add_tag("has_memory_intensive_reco")

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} ttbar-semileptonic datasets.")

def add_tt_dl_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds ttbar_dl datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag
    tt_names = [
        "tt_dl_powheg",
    ]
    datasets = {
        2: {
            "2017": tt_names,
        },
        3: {
            "2022preEE": tt_names,
            "2022postEE": tt_names,
            "2023preBPix": tt_names,
            "2023postBPix": tt_names,
            "2024": tt_names,
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"TTbar - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag({"has_top", "has_ttbar", "is_sm_ttbar"})
        if ds.name.startswith("tt_sl"):
            ds.add_tag("has_memory_intensive_reco")

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} ttbar-dileptonic datasets.")

def add_tt_fh_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds ttbar_sl datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag
    tt_names = [
        "tt_fh_powheg",
    ]
    datasets = {
        2: {
            "2017": tt_names,
        },
        3: {
            "2022preEE": tt_names,
            "2022postEE": tt_names,
            "2023preBPix": tt_names,
            "2023postBPix": tt_names,
            "2024": tt_names,
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"TTbar - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag({"has_top", "has_ttbar", "is_sm_ttbar"})
        if ds.name.startswith("tt_sl"):
            ds.add_tag("has_memory_intensive_reco")

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} ttbar-fully hadronic datasets.")

def add_st_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds single top datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag

    datasets = {
        2: {
            "2017": [
                "st_schannel_lep_4f_amcatnlo",
                "st_schannel_had_4f_amcatnlo",
                "st_tchannel_t_4f_powheg",
                "st_tchannel_tbar_4f_powheg",
                "st_twchannel_t_powheg",
                "st_twchannel_tbar_powheg",
            ],
        },
        3: {
            "2022preEE": [
                "st_tchannel_t_4f_powheg",
                "st_tchannel_tbar_4f_powheg",
                "st_twchannel_t_sl_powheg",
                "st_twchannel_tbar_sl_powheg",
                "st_twchannel_t_dl_powheg",
                "st_twchannel_tbar_dl_powheg",
                "st_twchannel_t_fh_powheg",
                "st_twchannel_tbar_fh_powheg",
            ],
            "2022postEE": [
                "st_tchannel_t_4f_powheg",
                "st_tchannel_tbar_4f_powheg",
                "st_twchannel_t_sl_powheg",
                "st_twchannel_tbar_sl_powheg",
                "st_twchannel_t_dl_powheg",
                "st_twchannel_tbar_dl_powheg",
                "st_twchannel_t_fh_powheg",
                "st_twchannel_tbar_fh_powheg",
            ],
            "2023preBPix": [
                "st_tchannel_t_4f_powheg",
                "st_tchannel_tbar_4f_powheg",
                "st_twchannel_t_sl_powheg",
                "st_twchannel_tbar_sl_powheg",
                "st_twchannel_t_dl_powheg",
                "st_twchannel_tbar_dl_powheg",
                "st_twchannel_t_fh_powheg",
                "st_twchannel_tbar_fh_powheg",
            ],
            "2023postBPix": [
                "st_tchannel_t_4f_powheg",
                "st_tchannel_tbar_4f_powheg",
                "st_twchannel_t_sl_powheg",
                "st_twchannel_tbar_sl_powheg",
                "st_twchannel_t_dl_powheg",
                "st_twchannel_tbar_dl_powheg",
                "st_twchannel_t_fh_powheg",
                "st_twchannel_tbar_fh_powheg",
            ],
            "2024": [
                # t channel
                # "st_tchannel_t_had_4f_powheg",  # FIXME one broken file stuck at CalibrateEvents?
                "st_tchannel_tbar_had_4f_powheg",
                "st_tchannel_t_lep_4f_powheg",
                "st_tchannel_tbar_lep_4f_powheg",
                # tW channel
                "st_twchannel_t_sl_powheg",
                "st_twchannel_tbar_sl_powheg",
                "st_twchannel_t_dl_powheg",
                "st_twchannel_tbar_dl_powheg",
                "st_twchannel_t_fh_powheg",
                "st_twchannel_tbar_fh_powheg",
            ],
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"Single Top - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag("has_top")

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} single top datasets.")


def add_qcd_datasets(
        config: od.Config,
        limit_dataset_files: int | None = None,
        log: bool = False,
) -> None:
    """
    Adds QCD datasets to the config based on the run number and campaign tag.
    """
    run = config.campaign.x.run
    tag = config.x.cpn_tag

    datasets = {
        2: {
            "2017": [
                "qcd_ht50to100_madgraph",
                "qcd_ht100to200_madgraph",
                "qcd_ht200to300_madgraph",
                "qcd_ht300to500_madgraph",
                "qcd_ht500to700_madgraph",
                "qcd_ht700to1000_madgraph",
                "qcd_ht1000to1500_madgraph",
                "qcd_ht1500to2000_madgraph",
                "qcd_ht2000toinf_madgraph",
            ],
        },
        3: {
            "2022preEE": [
                "qcd_ht70to100_madgraph",  # FIXME AssertionError (med. stat.)
                # "qcd_ht100to200_madgraph",  # FIXME no xs for 13.6 in https://xsdb-temp.app.cern.ch/xsdb/?columns=67108863&currentPage=0&pageSize=10&searchQuery=DAS%3DQCD-4Jets_HT-100to200_TuneCP5_13p6TeV_madgraphMLM-pythia8  # noqa
                "qcd_ht200to400_madgraph",  # FIXME AssertionError (lim. stat.)
                "qcd_ht400to600_madgraph",
                "qcd_ht600to800_madgraph",  # FIXME AssertionError (lim. stat.)
                "qcd_ht800to1000_madgraph",
                "qcd_ht1000to1200_madgraph",
                "qcd_ht1200to1500_madgraph",
                "qcd_ht1500to2000_madgraph",
                "qcd_ht2000toinf_madgraph",
            ],
            "2022postEE": [  # Same as preEE
                "qcd_ht70to100_madgraph",  # FIXME AssertionError (lim. stat.)
                # "qcd_ht100to200_madgraph",  # FIXME no xs for 13.6 in https://xsdb-temp.app.cern.ch/xsdb/?columns=67108863&currentPage=0&pageSize=10&searchQuery=DAS%3DQCD-4Jets_HT-100to200_TuneCP5_13p6TeV_madgraphMLM-pythia8  # noqa
                "qcd_ht200to400_madgraph",  # FIXME AssertionError (lim. stat.)
                "qcd_ht400to600_madgraph",
                "qcd_ht600to800_madgraph",  # FIXME AssertionError (lim. stat.)
                "qcd_ht800to1000_madgraph",
                "qcd_ht1000to1200_madgraph",
                "qcd_ht1200to1500_madgraph",
                "qcd_ht1500to2000_madgraph",
                "qcd_ht2000toinf_madgraph",
            ],
            "2024": [
                # "qcd_ht40to70_madgraph",  # FIXME empty after selection (lim. config)
                # "qcd_ht70to100_madgraph",  # FIXME empty after selection (lim. config)
                # "qcd_ht100to200_madgraph",  # FIXME empty after selection (lim. config)
                "qcd_ht200to400_madgraph",
                "qcd_ht400to600_madgraph",
                "qcd_ht600to800_madgraph",
                "qcd_ht800to1000_madgraph",
                "qcd_ht1000to1200_madgraph",
                "qcd_ht1200to1500_madgraph",
                "qcd_ht1500to2000_madgraph",
                "qcd_ht2000toinf_madgraph",
            ],
        },
    }
    try:
        dataset_list = datasets[run][tag]
    except KeyError:
        raise ValueError(f"QCD - Unsupported run/tag combination: run={run}, tag={tag}")

    for dataset in dataset_list:
        ds = config.add_dataset(config.campaign.get_dataset(dataset))
        ds.add_tag("is_qcd")

        if limit_dataset_files:
            for info in ds.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

    if log:
        logger.info(f"Added {len(dataset_list)} QCD datasets.")
