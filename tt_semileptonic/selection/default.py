# coding: utf-8

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult
from columnflow.production.cms.mc_weight import mc_weight
from columnflow.production.processes import process_ids
from columnflow.production.categories import category_ids

from operator import and_
from functools import reduce

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")
np = maybe_import("numpy")

from collections import defaultdict, OrderedDict

from columnflow.selection.cms.met_filters import met_filters
from columnflow.selection.cms.json_filter import json_filter
from columnflow.selection.cms.jets import jet_veto_map

from tt_semileptonic.selection.jets import jet_selection
from tt_semileptonic.selection.leptons import lepton_selection
from tt_semileptonic.selection.met import met_selection
from tt_semileptonic.selection.lepton_jet_2d import lepton_jet_2d_selection
from tt_semileptonic.selection.fatjets import top_tagged_jets
from tt_semileptonic.production.lepton import lepton_producer

# Order of selection is:
# - MET filters                      -> step "METFilters"
# - JSON filter (data only)          -> step "JSON"
# - lepton selection                 -> steps "lepton", "dilepton_veto"
#   (columns added by production.lepton.lepton_definition: Muon/Electron.pass_lepton,
#    Muon/Electron.pass_veto_lepton, channel_id, pt_regime)
# - jet selection                    -> steps "jet", "bjet"
# - MET selection                    -> step "met"
# - lepton-jet 2D cut                -> step "lepton_jet_2d"
# - lepton_producer builds the Lepton column
# - AK8 top tagging / all-hadronic veto -> step "all_had_veto"
# - jet veto map (data + MC)         -> step "jet_veto_map"
# (everything after the lepton selection is channel-dependent, so it runs after it)


# Implement the task to update the stats object

@selector(uses={"process_id", "mc_weight"})
def custom_increment_stats(
    self: Selector,
    events: ak.Array,
    results: SelectionResult,
    stats: dict,
    **kwargs,
) -> ak.Array:
    """
    Unexposed selector that does not actually select objects but instead increments selection
    *stats* in-place based on all input *events* and the final selection *mask*.
    """
    # get event masks
    event_mask = results.event

    # increment plain counts
    stats["num_events"] += len(events)
    stats["num_events_selected"] += float(ak.sum(event_mask, axis=0))

    # get a list of unique process ids present in the chunk
    unique_process_ids = np.unique(events.process_id)

    # per-process event counts: required by columnflow's `normalization_weights` producer,
    # which is run for MC inside cf.MergeSelectionMasks and reads `num_events_per_process`
    # from the merged selection stats (a KeyError here breaks the whole plotting chain)
    stats.setdefault("num_events_per_process", defaultdict(int))
    stats.setdefault("num_events_selected_per_process", defaultdict(int))
    for p in unique_process_ids:
        proc_mask = events.process_id == p
        stats["num_events_per_process"][int(p)] += int(ak.sum(proc_mask))
        stats["num_events_selected_per_process"][int(p)] += int(ak.sum(proc_mask & event_mask))

    # create a map of entry names to (weight, mask) pairs that will be written to stats
    weight_map = OrderedDict()
    if self.dataset_inst.is_mc:
        # mc weight for all events
        weight_map["mc_weight"] = (events.mc_weight, Ellipsis)

        # mc weight for selected events
        weight_map["mc_weight_selected"] = (events.mc_weight, event_mask)

    # get and store the sum of weights in the stats dictionary
    for name, (weights, mask) in weight_map.items():
        joinable_mask = True if mask is Ellipsis else mask

        # sum of different weights in weight_map for all processes
        stats[f"sum_{name}"] += float(ak.sum(weights[mask]))

        # sums per process id
        stats.setdefault(f"sum_{name}_per_process", defaultdict(float))
        for p in unique_process_ids:
            stats[f"sum_{name}_per_process"][int(p)] += float(ak.sum(
                weights[(events.process_id == p) & joinable_mask],
            ))

    return events, results


# Now create the exposed Selector using the three above defined Selectors

@selector(
    # some information for Selector
    # e.g., if we want to use some internal Selector, make
    # sure that you have all the relevant information
    uses={
        met_filters, json_filter, jet_veto_map,
        mc_weight, jet_selection, lepton_selection, met_selection, lepton_jet_2d_selection,
        top_tagged_jets, custom_increment_stats,
        process_ids,
        category_ids,
        lepton_producer
    },
    produces={
        # jet_selection / top_tagged_jets / jet_veto_map now write real columns
        # (Jet.jetId / FatJet.jetId / Jet.veto_map_mask), so they must be listed here
        # too, not just in `uses`, for those columns to be kept
        mc_weight, lepton_selection, jet_selection, top_tagged_jets, jet_veto_map,
        process_ids, category_ids, lepton_producer
    },

    # this is our top level Selector, so we need to make it reachable
    # for the SelectEvents task
    exposed=True,
)
def default(
    self: Selector,
    events: ak.Array,
    stats: defaultdict,
    **kwargs,
) -> tuple[ak.Array, SelectionResult]:
    results = SelectionResult()

    # MET filters
    events, met_filters_results = self[met_filters](events, **kwargs)
    results.steps.METFilters = met_filters_results.steps.met_filter

    # golden JSON (certified good luminosity blocks) -- data only, no MC equivalent
    if self.dataset_inst.is_data:
        events, json_filter_results = self[json_filter](events, **kwargs)
        results.steps.JSON = json_filter_results.steps.json

    # add corrected mc weights to be used later for plotting and to calculate the sum saved in stats
    if self.dataset_inst.is_mc:
        events = self[mc_weight](events, **kwargs)

    # lepton selection: decides the channel (writes the `channel_id` / `pt_regime` columns)
    # -> must run before jet_selection, whose leading-jet pt cut is channel-dependent
    events, lepton_results = self[lepton_selection](events, **kwargs)
    results += lepton_results

    # jet selection (uses channel_id)
    events, jet_results = self[jet_selection](events, **kwargs)
    results += jet_results

    # MET selection (uses channel_id)
    events, met_results = self[met_selection](events, **kwargs)
    results += met_results

    # lepton-jet 2D cut (replaces isolation for high-pt leptons)
    events, l2d_results = self[lepton_jet_2d_selection](events, **kwargs)
    results += l2d_results

    # merge Muon/Electron into a single `Lepton` collection based on `channel_id`
    events = self[lepton_producer](events, **kwargs)

    # AK8 top tagging + all-hadronic veto (reads the Lepton column above)
    events, top_tag_results = self[top_tagged_jets](events, **kwargs)
    results += top_tag_results

    # jet veto map: reject events with a jet in a known-bad detector region (data + MC).
    # reads Jet.jetId (tightLepVeto bit, Run 3), already recomputed by jet_selection above.
    events, jet_veto_results = self[jet_veto_map](events, **kwargs)
    results += jet_veto_results

    events = self[category_ids](events, results=results, **kwargs) # needs categories

    # combined event selection after all steps
    event_sel = reduce(and_, results.steps.values())
    results.event = event_sel

    # create process ids, used by custom_increment_stats
    events = self[process_ids](events, **kwargs)

    # use increment stats selector to update dictionary to be saved in json format
    events, results = self[custom_increment_stats](events, results, stats, **kwargs)

    return events, results