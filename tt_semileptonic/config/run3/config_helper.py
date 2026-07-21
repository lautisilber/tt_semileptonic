#
# Creates config for the tt_semileptonic analysis
#

from __future__ import annotations
import functools
import os
import yaml
from scinum import Number
from columnflow.config_util import (
    get_root_processes_from_campaign, add_shift_aliases, get_shifts_from_sources, verify_config_processes,
)
from columnflow.cms_util import CATInfo, CATSnapshot
from columnflow.util import DotDict

import tt_semileptonic.config.datasets_helper as datasets_helper
import tt_semileptonic.config.defaults_and_groups_helper as defaults_and_groups_helper
import tt_semileptonic.config.categories_helper as categories_helper
import tt_semileptonic.config.variables_helper as variables_helper
import tt_semileptonic.config.taggers_helper as taggers_helper
import tt_semileptonic.config.corrections_helper as corrections_helper

thisdir = os.path.dirname(os.path.abspath(__file__))

def get_datasets(
    campaign: od.Campaign,
) -> list[str]:
    """
    Get all dataset names from the campaign without creating full config objects.
    """
    return list(campaign.datasets)

def create_new_config(
    analysis: od.Analysis,
    campaign: od.Campaign,
    config_name: str,
    config_id: int,
    limit_dataset_files: int | None = None
) -> od.Config:
    """
    Configurable function for creating a config for a run3 analysis given
    a base *analysis* object and a *campaign* (i.e. set of datasets).
    """

    year = campaign.x.year
    vnano = campaign.x.version

    if campaign.x.year not in [2022, 2023, 2024]:
        raise NotImplementedError(f"Year f{year} is not implemented")

    corr_postfix = ""
    if year == 2022:
        corr_postfix = f"{campaign.x.EE}EE"
    elif year == 2023:
        corr_postfix = f"{campaign.x.BPix}BPix"

    # create config
    cfg = analysis.add_config(campaign, name=config_name, id=config_id)

    # add tags to config
    cfg.x.run = 3
    cfg.x.cpn_tag = f"{year}{corr_postfix}"
    cfg.x.year = year

    # add datasets
    log = True
    procs = get_root_processes_from_campaign(campaign)

    cfg.add_process(procs.n.data)
    datasets_helper.add_data_datasets(cfg, limit_dataset_files, log)

    cfg.add_process(procs.n.dy)
    datasets_helper.add_dy_datasets(cfg, limit_dataset_files, log)

    cfg.add_process(procs.n.w_lnu)
    datasets_helper.add_w_lnu_datasets(cfg, limit_dataset_files, log)

    cfg.add_process(procs.n.vv)
    datasets_helper.add_vv_datasets(cfg, limit_dataset_files, log)

    cfg.add_process(procs.n.tt_sl)
    datasets_helper.add_tt_sl_datasets(cfg, limit_dataset_files, log)
    cfg.add_process(procs.n.tt_dl)
    datasets_helper.add_tt_dl_datasets(cfg, limit_dataset_files, log)
    cfg.add_process(procs.n.tt_fh)
    datasets_helper.add_tt_fh_datasets(cfg, limit_dataset_files, log)
    # Otherwise these will be combined into a single "tt" process
    # https://columnflow.readthedocs.io/en/stable/user_guide/plotting.html#customization-of-plots
    # config.x.process_settings_groups = {
    #     # "unstack_processes": {proc: {"unstack": True} for proc in ("tt_sl", "tt_dl", "tt_fh")},
    #     "unstack_processes": {"tt": {"unstack": True}},
    # }

    cfg.add_process(procs.n.st)
    datasets_helper.add_st_datasets(cfg, limit_dataset_files, log)

    cfg.add_process(procs.n.qcd)
    datasets_helper.add_qcd_datasets(cfg, limit_dataset_files, log)

    colors = {
        "data": "#000000",  # black
        "tt_sl": "#E02E21", # dark red
        "tt_dl": "#E07721", # orange
        "tt_fh": "#E0B721", # yellow
        "qcd": "#5E8FFC",  # blue
        "w_lnu": "#82FF28",  # green
        "higgs": "#984ea3",  # purple
        "st": "#3E00FB",  # dark purple
        "dy": "#FBFF36",  # yellow
        "vv": "#B900FC",  # pink
        "other": "#999999",  # grey
    }

    # verify that the root processes of each dataset (or one of their
    # ancestor processes) are registered in the config
    verify_config_processes(cfg, warn=True)

    cfg.x.btag_wp = taggers_helper.btag_params(cfg)
    cfg.x.toptag_wp = taggers_helper.toptag_params(cfg)

    # lepton selection parameters
    cfg.x.lepton_selection = DotDict.wrap({
        "mu": {
            "column": "Muon",
            "min_pt": {
                "low_pt": 30,
                "high_pt": 55,
            },
            "max_abseta": 2.4,
            "iso": {
                "column": "pfIsoId",
                "min_value": 4,  # 1 = PFIsoVeryLoose, 2 = PFIsoLoose, 3 = PFIsoMedium, 4 = PFIsoTight, 5 = PFIsoVeryTight, 6 = PFIsoVeryVeryTight  # noqa
            },
            "id": {
                "low_pt": {
                    "column": "tightId",
                    "value": True,
                },
                "high_pt": {
                    "column": "highPtId",
                    "value": 2,  # 2 = global high pT, which includes tracker high pT
                },
            },
            # veto events with additional leptons passing looser cuts
            "min_pt_addveto": 25,
            "id_addveto": {
                "column": "tightId",
                "value": True,
            },
            "max_abseta_addveto": 2.4,
        },
        "e": {
            "column": "Electron",
            "min_pt": {
                "low_pt": 35,
                "high_pt": 120,
            },
            "max_abseta": 2.5,
            "barrel_veto": [1.44, 1.57],
            "mva_id": {
                "low_pt": "mvaIso_WP80",
                "high_pt": "mvaNoIso_WP80",
            },
            # veto events with additional leptons passing looser cuts
            "min_pt_addveto": 25,
            "id_addveto": {
                "column": "cutBased",
                "min_value": 3,  # 0 = fail, 1 = veto, 2 = loose, 3 = medium, 4 = tight
            },
            "max_abseta_addveto": 2.5,
        },
    })

    # jet selection parameters
    cfg.x.jet_selection = DotDict.wrap({
        "ak4": {
            "column": "Jet",
            "max_abseta": 2.5,
            "min_pt": {
                "baseline": 30,
                "e": [50, 40],
                "mu": [50, 50],
            },
            "btagger": {
                "column": "btagDeepFlavB" if year != 2024 else "btagUParTAK4B",
                # "column": "btagDeepFlavB" if year != 2024 else "btagPNetB",
                "wp": cfg.x.btag_wp.deepjet.medium if year != 2024 else cfg.x.btag_wp.UParTAK4.medium,
                # "wp": config.x.btag_wp.deepjet.medium if year != 2024 else config.x.btag_wp.particle_net.medium,
            },
        },
        "ak8": {
            "column": "FatJet",
            "max_abseta": 2.5,
            "min_pt": {
                "baseline": 200,
                "toptagged": 400,
            },
            "msoftdrop": [105, 210],
            "toptagger": {
                "column": ["particleNetWithMass_TvsQCD"] if year != 2024 else [
                    "globalParT3_TopbWqq",
                    "globalParT3_TopbWq",
                    "globalParT3_QCD",
                ],
                "wp": cfg.x.toptag_wp.particle_net.tight if year != 2024 else cfg.x.toptag_wp.GloParTv3.tight,
            },
            "delta_r_lep": 0.8,
        },
    })

    # MET selection parameters
    cfg.x.met_selection = DotDict.wrap({
        "column": "PuppiMET",
        "raw_column": "RawPuppiMET",
        "min_pt": {
            "e": 60,
            "mu": 70,
        },
    })

    # lepton jet 2D isolation parameters
    cfg.x.lepton_jet_iso = DotDict.wrap({
        "min_pt": 15,
        "min_delta_r": 0.4,
        "min_pt_rel": 25,
    })

    # MET filters
    # https://twiki.cern.ch/twiki/bin/viewauth/CMS/MissingETOptionalFiltersRun2#Run_3_recommendations
    cfg.x.met_filters = {
        "Flag.goodVertices",
        "Flag.globalSuperTightHalo2016Filter",
        "Flag.EcalDeadCellTriggerPrimitiveFilter",
        "Flag.BadPFMuonFilter",
        "Flag.BadPFMuonDzFilter",
        "Flag.hfNoisyHitsFilter",
        "Flag.eeBadScFilter",
        "Flag.ecalBadCalibFilter",
    }

    # lumi values in inverse pb
    # https://twiki.cern.ch/twiki/bin/viewauth/CMS/PdmVRun3Analysis
    if year == 2022 and campaign.x.EE == "pre":
        cfg.x.luminosity = Number(7_980.4541, {
            "lumi_13p6TeV_2022": 0.014j,
        })
    elif year == 2022 and campaign.x.EE == "post":
        cfg.x.luminosity = Number(26_671.6097, {
            "lumi_13p6TeV_2022": 0.014j,
        })
    elif year == 2023 and campaign.x.BPix == "pre":
        cfg.x.luminosity = Number(18_062.6591, {
            "lumi_13p6TeV_2023": 0.013j,
        })
    elif year == 2023 and campaign.x.BPix == "post":
        cfg.x.luminosity = Number(9_693.1301, {
            "lumi_13p6TeV_2023": 0.013j,
        })
    elif year == 2024:
        cfg.x.luminosity = Number(109_080.0, {  # TODO: update number
            "lumi_13p6TeV_2024": 0.013j,
        })
        # processed lumi for limited configs
        # config.x.luminosity = Number(995.223558512, {
        #     "lumi_13p6TeV_2024": 0.013j,
        # })
    else:
        raise NotImplementedError(f"Luminosity for year {year} is not defined.")

    # ttbar reconstruction parameters
    #
    # chi2 tuning parameters (mean masses/widths of top quarks
    # with hadronically/leptonically decaying W bosons)
    # AN2019_197_v3
    # TODO: update to Run 3 values
    cfg.x.chi2_parameters = DotDict.wrap({
        "resolved": {
            "m_had": 175.4,  # GeV
            "s_had": 20.7,  # GeV
            "m_lep": 175.0,  # GeV
            "s_lep": 23.3,  # GeV
        },
        "boosted": {
            "m_had": 182.3,  # GeV
            "s_had": 16.1,  # GeV
            "m_lep": 172.2,  # GeV
            "s_lep": 21.7,  # GeV
        },
    })

    # parameters to fine-tune the ttbar combinatoric
    # reconstruction
    cfg.x.ttbar_reco_settings = DotDict.wrap({
        # -- minimal settings (fast runtime)
        # "n_jet_max": 9,
        # "n_jet_lep_range": (1, 1),
        # "n_jet_had_range": (3, 3),
        # "n_jet_ttbar_range": (4, 4),
        # "max_chunk_size": 100000,

        # -- default settings
        "n_jet_max": 9,
        "n_jet_lep_range": (1, 2),
        "n_jet_had_range": (1, 6),
        "n_jet_ttbar_range": (2, 6),
        "max_chunk_size": (
            lambda dataset_inst:
                10000 if dataset_inst.has_tag("has_memory_intensive_reco")
                else 30000
        ),

        # -- "maxed out" settings (very slow)
        # "n_jet_max": 10,
        # "n_jet_lep_range": (1, 8),
        # "n_jet_had_range": (1, 9),
        # "n_jet_ttbar_range": (2, 10),
        # "max_chunk_size": 10000,
    })

    #
    # systematic shifts
    #

    # read in JEC sources from file
    with open(os.path.join(thisdir, "jec_sources.yaml"), "r") as f:
        all_jec_sources = yaml.load(f, yaml.Loader)["names"]

    # declare the shifts
    def add_shifts(config):
        # nominal shift
        config.add_shift(name="nominal", id=0)

        # tune shifts are covered by dedicated, varied datasets, so tag the shift as "disjoint_from_nominal"
        # (this is currently used to decide whether ML evaluations are done on the full shifted dataset)
        config.add_shift(name="tune_up", id=1, type="shape", tags={"disjoint_from_nominal"})
        config.add_shift(name="tune_down", id=2, type="shape", tags={"disjoint_from_nominal"})

        config.add_shift(name="hdamp_up", id=3, type="shape", tags={"disjoint_from_nominal"})
        config.add_shift(name="hdamp_down", id=4, type="shape", tags={"disjoint_from_nominal"})

        # pileup / minimum bias cross section variations
        config.add_shift(name="minbias_xs_up", id=7, type="shape")
        config.add_shift(name="minbias_xs_down", id=8, type="shape")
        add_shift_aliases(config, "minbias_xs", {"pu_weight": "pu_weight_{name}"})

        # top pt reweighting
        config.add_shift(name="top_pt_up", id=9, type="shape")
        config.add_shift(name="top_pt_down", id=10, type="shape")
        add_shift_aliases(config, "top_pt", {"top_pt_weight": "top_pt_weight_{direction}"})

        # renormalization scale
        config.add_shift(name="mur_up", id=901, type="shape")
        config.add_shift(name="mur_down", id=902, type="shape")

        # factorization scale
        config.add_shift(name="muf_up", id=903, type="shape")
        config.add_shift(name="muf_down", id=904, type="shape")

        # scale variation (?)
        config.add_shift(name="scale_up", id=905, type="shape")
        config.add_shift(name="scale_down", id=906, type="shape")

        # pdf variations
        config.add_shift(name="pdf_up", id=951, type="shape")
        config.add_shift(name="pdf_down", id=952, type="shape")

        # alpha_s variation
        config.add_shift(name="alpha_up", id=961, type="shape")
        config.add_shift(name="alpha_down", id=962, type="shape")

        # TODO: murf_envelope?
        for unc in ["mur", "muf", "scale", "pdf", "alpha"]:
            add_shift_aliases(config, unc, {
                # TODO: normalized?
                f"{unc}_weight": f"{unc}_weight_{{direction}}",
            })

        # event weights due to muon scale factors
        if not config.has_tag("skip_muon_weights"):
            config.add_shift(name="muon_up", id=111, type="shape")
            config.add_shift(name="muon_down", id=112, type="shape")
            add_shift_aliases(config, "muon", {"muon_weight": "muon_weight_{direction}"})

        # event weights due to electron scale factors
        if not config.has_tag("skip_electron_weights"):
            config.add_shift(name="electron_up", id=121, type="shape")
            config.add_shift(name="electron_down", id=122, type="shape")
            add_shift_aliases(config, "electron", {"electron_weight": "electron_weight_{direction}"})

        # V+jets reweighting
        config.add_shift(name="vjets_up", id=201, type="shape")
        config.add_shift(name="vjets_down", id=202, type="shape")
        add_shift_aliases(config, "vjets", {"vjets_weight": "vjets_weight_{direction}"})

        # b-tagging shifts
        if year != 2024:
            btag_uncs = [
                "hf", "lf",
                "hfstats1", "hfstats2",
                "lfstats1", "lfstats2",
                "cferr1", "cferr2",
            ]
            for i, unc in enumerate(btag_uncs):
                config.add_shift(name=f"btag_{unc}_up", id=501 + 2 * i, type="shape")
                config.add_shift(name=f"btag_{unc}_down", id=502 + 2 * i, type="shape")
                add_shift_aliases(
                    config,
                    f"btag_{unc}",
                    {
                        # PREVIOUS IMPLEMENTATION (still used in some configs?)
                        # taken from
                        # https://github.com/uhh-cms/hh2bbww/blob/c6d4ee87a5c970660497e52aed6b7ebe71125d20/hbw/config/config_run2.py#L421
                        "normalized_btag_weight": f"normalized_btag_weight_{unc}_" + "{direction}",
                        "normalized_njet_btag_weight": f"normalized_njet_btag_weight_{unc}_" + "{direction}",
                        "btag_weight": f"btag_weight_{unc}_" + "{direction}",
                        "njet_btag_weight": f"njet_btag_weight_{unc}_" + "{direction}",
                    },
                )
        else:
            # https://cms-analysis-corrections.docs.cern.ch/corrections_era/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/BTV/2025-08-19/#btagging_preliminaryjsongz  # noqa
            btag_uncs = [
                "fsrdef", "isrdef",
                "hdamp", "jer", "jes",
                "mass", "statistic",
                "tune",
            ]
            for i, unc in enumerate(btag_uncs):
                config.add_shift(name=f"btag_{unc}_up", id=501 + 2 * i, type="shape")
                config.add_shift(name=f"btag_{unc}_down", id=502 + 2 * i, type="shape")
                add_shift_aliases(
                    config,
                    f"btag_{unc}",
                    {
                        # UPDATED FOR 2024 USING UParTAK4B for b-tagging
                        "normalized_btag_weight_upart": f"btagUParTAK4B_shape_weight_{unc}_" + "{direction}",
                        "normalized_njet_btag_weight_upart": f"btagUParTAK4B_shape_weight_{unc}_" + "{direction}",
                    },
                )

        # jet energy scale (JEC) uncertainty variations
        for jec_source in config.x.jec.Jet.uncertainty_sources:
            idx = all_jec_sources.index(jec_source)
            config.add_shift(name=f"jec_{jec_source}_up", id=5000 + 2 * idx, type="shape", tags={"jec"})
            config.add_shift(name=f"jec_{jec_source}_down", id=5001 + 2 * idx, type="shape", tags={"jec"})
            add_shift_aliases(
                config,
                f"jec_{jec_source}",
                {
                    "Jet.pt": "Jet.pt_{name}",
                    "Jet.mass": "Jet.mass_{name}",
                    "MET.pt": "MET.pt_{name}",
                },
            )

        # jet energy resolution (JER) scale factor variations
        config.add_shift(name="jer_up", id=6000, type="shape")
        config.add_shift(name="jer_down", id=6001, type="shape")
        add_shift_aliases(
            config,
            "jer",
            {
                "Jet.pt": "Jet.pt_{name}",
                "Jet.mass": "Jet.mass_{name}",
                "MET.pt": "MET.pt_{name}",
            },
        )

        # PSWeight variations
        config.add_shift(name="ISR_up", id=7001, type="shape")  # PS weight [0] ISR=2 FSR=1
        config.add_shift(name="ISR_down", id=7002, type="shape")  # PS weight [2] ISR=0.5 FSR=1
        add_shift_aliases(config, "ISR", {"ISR": "ISR_{direction}"})

        config.add_shift(name="FSR_up", id=7003, type="shape")  # PS weight [1] ISR=1 FSR=2
        config.add_shift(name="FSR_down", id=7004, type="shape")  # PS weight [3] ISR=1 FSR=0.5
        add_shift_aliases(config, "FSR", {"FSR": "FSR_{direction}"})

    #
    # corrections
    #

    cfg.x.vjets_reweighting = corrections_helper.vjets_reweighting_cfg()
    cfg.x.jec, cfg.x.jer = corrections_helper.jerc_cfg(campaign, year)
    # add the shifts
    add_shifts(cfg)

    cfg.x.btag_sf = corrections_helper.btag_sf_cfg(year)
    cfg.x.toptag_sf = corrections_helper.toptag_sf_cfg()

    cfg.x.electron_sf = corrections_helper.lepton_sf_cfg(cfg, "electron")

    cfg.x.muon_sf_names = corrections_helper.lepton_sf_cfg(cfg, "muon")[0]
    cfg.x.muon_id_sf_names = corrections_helper.lepton_sf_cfg(cfg, "muon")[1]
    cfg.x.muon_iso_sf_names = corrections_helper.lepton_sf_cfg(cfg, "muon")[2]

    cfg.x.met_phi_correction = corrections_helper.met_phi_cfg(cfg)  # METPhiConfig object
    cfg.x.jet_id = corrections_helper.jet_id_cfg()["Jet"]  # JetIdConfig object
    cfg.x.fatjet_id = corrections_helper.jet_id_cfg()["FatJet"]  # JetIdConfig object

    # top pt reweighting parameters
    # https://twiki.cern.ch/twiki/bin/viewauth/CMS/TopPtReweighting#TOP_PAG_corrections_based_on_dat?rev=31
    cfg.x.top_pt_reweighting_params = {
        "a": 0.0615,
        "b": -0.0005,
    }

    #
    # event weights
    #

    # event weight columns as keys in an OrderedDict, mapped to shift instances they depend on
    get_shifts = functools.partial(get_shifts_from_sources, cfg)
    cfg.x.event_weights = DotDict({
        "normalization_weight": [],
        "pu_weight": get_shifts("minbias_xs"),
        "muon_weight": get_shifts("muon"),
        "electron_weight": get_shifts("electron"),
        # "ISR": get_shifts("ISR"),
        # "FSR": get_shifts("FSR"),
        # TODO: add scale and PDF weights, where available
        # "scale_weight": ???,
        # "pdf_weight": ???,
    })

    # event weights only present in certain datasets
    for dataset in cfg.datasets:
        dataset.x.event_weights = DotDict()

        # TTbar: top pt reweighting
        if dataset.has_tag("is_ttbar"):
            dataset.x.event_weights["top_pt_weight"] = get_shifts("top_pt")

        # V+jets: QCD NLO reweighting (disable for now)
        # if dataset.has_tag("is_v_jets"):
        #     dataset.x.event_weights["vjets_weight"] = get_shifts("vjets")

    #
    # external files
    # setup taken from https://github.com/uhh-cms/hh2bbtautau/blob/ed8f363ac239b0257fc7f470b96f5c09a0572c34/hbt/config/configs_hbt.py#L1574  # noqa: E501
    # https://cms-analysis-corrections.docs.cern.ch
    #

    cfg.x.external_files = DotDict()

    # helper
    def add_external(name, value):
        if isinstance(value, dict):
            value = DotDict.wrap(value)
        cfg.x.external_files[name] = value

    # prepare run/era/nano meta data info to determine files in the CAT metadata structure
    # see https://cms-analysis-corrections.docs.cern.ch
    cat_info = {
        (2022, "", 12): CATInfo(
            run=3,
            vnano=12,
            era="22CDSep23-Summer22",
            pog_directories={"dc": "Collisions22"},
            snapshot=CATSnapshot(btv="2025-08-20", dc="2025-07-25", egm="2025-04-15", jme="2025-09-23", lum="2024-01-31", muo="2025-08-14", tau="2025-10-01"),  # noqa: E501
        ),
        (2022, "EE", 12): CATInfo(
            run=3,
            vnano=12,
            era="22EFGSep23-Summer22EE",
            pog_directories={"dc": "Collisions22"},
            snapshot=CATSnapshot(btv="2025-08-20", dc="2025-07-25", egm="2025-04-15", jme="2025-10-07", lum="2024-01-31", muo="2025-08-14", tau="2025-10-01"),  # noqa: E501
        ),
        (2023, "", 12): CATInfo(
            run=3,
            vnano=12,
            era="23CSep23-Summer23",
            # pog_eras={"tau": "23CSep23-Summer22"},  # TODO: remove once typo in CAT repo is fixed
            pog_directories={"dc": "Collisions23"},
            snapshot=CATSnapshot(btv="2025-08-20", dc="2025-07-25", egm="2025-04-15", jme="2025-10-07", lum="2024-01-31", muo="2025-08-14", tau="2025-10-01"),  # noqa: E501
        ),
        (2023, "BPix", 12): CATInfo(
            run=3,
            vnano=12,
            era="23DSep23-Summer23BPix",
            pog_directories={"dc": "Collisions23"},
            snapshot=CATSnapshot(btv="2025-08-20", dc="2025-07-25", egm="2025-04-15", jme="2025-10-07", lum="2024-01-31", muo="2025-08-14", tau="2025-10-01"),  # noqa: E501
        ),
        (2024, "", 15): CATInfo(
            run=3,
            vnano=15,
            era="24CDEReprocessingFGHIPrompt-Summer24",
            pog_directories={"dc": "Collisions24"},
            snapshot=CATSnapshot(btv="2025-12-03", dc="2025-07-25", egm="2025-12-03", jme="2025-12-02", muo="2025-11-27", lum="2025-12-02"),  # noqa: E501
        ),
    }[(year, campaign.x.postfix, vnano)]
    cfg.x.cat_info = cat_info

    # common files
    # (versions in the end are for hashing in cases where file contents changed but paths did not)
    add_external("lumi", {
        "golden": {
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2022
            2022: (cat_info.get_file("dc", "Cert_Collisions2022_355100_362760_Golden.json"), "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2023
            2023: (cat_info.get_file("dc", "Cert_Collisions2023_366442_370790_Golden.json"), "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=180#Year_2024
            # not yet available at CAT space
            # 2024: (cat_info.get_file("dc", "Cert_Collisions2024_378981_386951_Golden.json"), "v1"),
            2024: ("https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions24/Cert_Collisions2024_378981_386951_Golden.json", "v1"),  # noqa: E501
        }[year],
        "normtag": {
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2022
            2022: ("/cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_BRIL.json", "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2023
            2023: ("/cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_BRIL.json", "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=180#Year_2024
            2024: ("/cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_BRIL.json", "v1"),  # TODO: correct?
        }[year],
    })

    # pileup weight corrections
    if year != 2024:  # TODO: not yet available, see https://cms-analysis-corrections.docs.cern.ch
        add_external("pu_sf", (cat_info.get_file("lum", "puWeights.json.gz"), "v1"))
    elif year == 2024:
        add_external("pu_sf", (cat_info.get_file("lum", "puWeights_BCDEFGHI.json.gz"), "v1"))

    # jet energy correction
    add_external("jet_jerc", (cat_info.get_file("jme", "jet_jerc.json.gz"), "v1"))

    # fat jet energy correction
    add_external("fat_jet_jerc", (cat_info.get_file("jme", "fat_jet_jerc.json.gz" if year != 2024 else "fatJet_jerc.json.gz"), "v1"))  # noqa: E501

    # jet veto map
    add_external("jet_veto_map", (cat_info.get_file("jme", "jetvetomaps.json.gz"), "v1"))

    # btag scale factor
    if year != 2024:
        add_external("btag_sf_corr", (cat_info.get_file("btv", "btagging.json.gz"), "v1"))
    else:
        # SF stored in preliminary file for 2024 for now?
        add_external("btag_sf_corr", (cat_info.get_file("btv", "btagging_preliminary.json.gz"), "v1"))  # noqa: E501

    # updated jet id
    add_external("jet_id", (cat_info.get_file("jme", "jetid.json.gz"), "v1"))

    # muon scale factors
    add_external("muon_sf", (cat_info.get_file("muo", "muon_Z.json.gz"), "v1"))

    # met phi correction
    if year != 2024:  # TODO: not yet available for 2024
        add_external("met_phi_corr", (cat_info.get_file("jme", f"met_xyCorrections_{year}_{year}{campaign.x.postfix}.json.gz"), "v1"))  # noqa: E501

    # electron scale factors
    add_external("electron_sf", (cat_info.get_file("egm", "electron.json.gz"), "v1"))
    # electron energy correction and smearing
    add_external("electron_ss", (cat_info.get_file("egm", "electronSS_EtDependent.json.gz"), "v1"))  # FIXME correct for us? # noqa: E501

    #
    # set defaults for
    # calibrator, selector etc
    # process, dataset, category, variable, shift groups
    #

    defaults_and_groups_helper.set_defaults(cfg)
    defaults_and_groups_helper.set_process_groups(cfg)
    defaults_and_groups_helper.set_dataset_groups(cfg)
    defaults_and_groups_helper.set_category_groups(cfg)
    defaults_and_groups_helper.set_variables_groups(cfg)
    defaults_and_groups_helper.set_shift_groups(cfg)
    defaults_and_groups_helper.set_selector_steps(cfg)

    # columns to keep after certain steps
    cfg.x.keep_columns = DotDict.wrap({
        "cf.MergeSelectionMasks": {
            "mc_weight", "normalization_weight", "process_id", "category_ids", "cutflow.*",
        },
        "cf.ReduceEvents": {
            #
            # NanoAOD columns
            #

            # general event info
            "run", "luminosityBlock", "event",

            # weights
            "genWeight",
            "LHEWeight.*",
            "LHEPdfWeight",
            "LHEScaleWeight",
            "PSWeight",

            # muons
            "{Muon,VetoMuon}.{pt,eta,phi,mass}",
            "Muon.pfRelIso04_all",
            # electrons
            "{Electron,VetoElectron}.{pt,eta,phi,mass}",
            "Electron.{deltaEtaSC,pfRelIso03_all}",

            # photons (for L1 prefiring)
            "Photon.{pt,eta,phi,mass,jetIdx}",

            # AK4 jets
            "{Jet,BJet,LightJet,LooseJet}.{pt,eta,phi,mass,btagDeepFlavB,hadronFlavour,btagUParTAK4B}",
            "Jet.rawFactor",

            # AK8 jets
            "{FatJet,FatJetTopTag,FatJetTopTagDeltaRLepton}.{pt,eta,phi,mass,rawFactor}",
            "{FatJet,FatJetTopTag}.{msoftdrop,particleNetWithMass_TvsQCD,deepTagMD_TvsQCD}",
            "FatJet.globalParT3.{TopbWqq,TopbWq,QCD}",
            "{FatJet,FatJetTopTag,FatJetTopTagDeltaRLepton}.{tau1,tau2,tau3}",
            "FatJetTopTagDeltaRLepton.msoftdrop",
            "FatJetTopTagDeltaRLepton.deepTagDeltaRLeptonMD_TvsQCD",

            # generator quantities
            "Generator.*",

            # generator particles
            "GenPart.*",

            # generator objects
            "GenMET.*",
            "GenJet.*",
            "GenJetAK8.*",

            # missing transverse momentum
            "PuppiMET.{pt,phi,significance,covXX,covXY,covYY}",
            "MET.{pt,phi,significance,covXX,covXY,covYY}",

            # number of primary vertices
            "PV.npvs",

            # average number of pileup interactions
            "Pileup.nTrueInt",

            #
            # columns added during selection
            #

            # generator particle info
            "GenTopDecay.*",
            "GenPartonTop.*",
            "GenVBoson.*",

            # generic leptons (merger of Muon/Electron)
            "Lepton.*",

            # columns for PlotCutflowVariables
            "cutflow.*",

            # other columns, required by various tasks
            "channel_id", "category_ids", "process_id",
            "deterministic_seed",
            "mc_weight",
            "pt_regime",
            "pu_weight*",
        },
    })

    # add channels
    cfg.add_channel("e", id=1)
    cfg.add_channel("mu", id=2)

    # add categories
    categories_helper.add_categories_selection(cfg)

    # add variables
    variables_helper.add_variables(cfg)

    return cfg
