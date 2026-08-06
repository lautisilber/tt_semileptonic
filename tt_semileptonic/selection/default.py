# coding: utf-8

"""
Default selection for m(ttbar).
"""

from operator import and_
from functools import reduce
from collections import defaultdict

from columnflow.util import maybe_import
from columnflow.calibration.cms.jets import ak_random
from columnflow.production.util import attach_coffea_behavior

from columnflow.selection import Selector, SelectionResult, selector
from columnflow.selection.stats import increment_stats
from columnflow.selection.cms.met_filters import met_filters
from columnflow.selection.cms.json_filter import json_filter
from columnflow.selection.cms.jets import jet_veto_map
# from columnflow.production.categories import category_ids
from columnflow.production.cms.mc_weight import mc_weight
from columnflow.production.processes import process_ids

# from mtt.selection.general import jet_energy_shifts
# from mtt.selection.lepton import lepton_selection
# from mtt.selection.cutflow_features import cutflow_features
# from mtt.selection.jets import jet_selection, top_tagged_jets, lepton_jet_2d_selection
# from mtt.selection.jets import met_selection
# from mtt.selection.qcd_spikes import qcd_spikes
# from mtt.selection.data_trigger_veto import data_trigger_veto


# from mtt.production.gen_top import gen_parton_top
# from mtt.production.gen_v import gen_v_boson

np = maybe_import("numpy")
ak = maybe_import("awkward")


@selector(
    produces={
        "event",
    }
)
def random_event_selector(
    self: Selector,
    events: ak.Array,
    **kwargs,
) -> tuple[ak.Array, SelectionResult]:
    rand_gen = np.random.default_rng(seed=1234)

    rand_selection = ak_random(
        ak.zeros_like(events.event, dtype=np.float32),
        ak.ones_like(events.event, dtype=np.float32),
        rand_func=rand_gen.uniform,
    )
    rand_selection = rand_selection < 0.5  # keep 50%, adjust as needed

    return events, SelectionResult(
        steps={"RandomSelection": rand_selection},
        event=rand_selection,
    )


@selector(
    uses={
        # category_ids,
        process_ids, increment_stats, attach_coffea_behavior,
        mc_weight,
        met_filters,
        # gen_parton_top,
        # gen_v_boson,
        json_filter,
        jet_veto_map,
        random_event_selector,
    },
    produces={
        # category_ids,
        process_ids, increment_stats, attach_coffea_behavior,
        mc_weight,
        met_filters,
        # gen_parton_top,
        # gen_v_boson,
        json_filter,
        jet_veto_map,
        random_event_selector,
    },
    exposed=True,
)
def default(
    self: Selector,
    events: ak.Array,
    stats: defaultdict,
    **kwargs,
) -> tuple[ak.Array, SelectionResult]:
    # ensure coffea behavior
    events = self[attach_coffea_behavior](events, **kwargs)

    # prepare the selection results that are updated at every step
    results = SelectionResult()

    # MET filters
    events, met_filters_results = self[met_filters](events, **kwargs)
    results.steps.METFilters = met_filters_results.steps.met_filter

    # random selection
    events, rand_results = self[random_event_selector](events, **kwargs)
    results += rand_results

    # combine all steps into the final event mask
    results.event = reduce(and_, results.steps.values())

    return events, results


# @default.init
# def default_init(self: Selector) -> None:

#     if hasattr(self, "dataset_inst") and self.dataset_inst.has_tag("is_qcd"):
#         self.uses |= {qcd_spikes}
#         self.produces |= {qcd_spikes}

#     if hasattr(self, "dataset_inst") and not self.dataset_inst.is_mc:
#         self.uses |= {data_trigger_veto}
#         self.produces |= {data_trigger_veto}
