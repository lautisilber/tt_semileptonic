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
from columnflow.columnar_util import set_ak_column

ak = maybe_import("awkward")
np = maybe_import("numpy")

from collections import defaultdict, OrderedDict

from tt_semileptonic.production.lepton import lepton_producer


# First, define an internal jet Selector to be used by the exposed Selector

@selector(
    # define some additional information here, e.g.
    # what columns are needed for this Selector?
    uses={
        "Jet.pt", "Jet.eta", "Jet.phi"
    },
    # does this Selector produce any columns?
    produces=set(),

    # pass any other variable to the selector class
    some_auxiliary_variable=True,
)
def jet_selection_with_result(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    # require an object of the Jet collection to have at least 20 GeV pt and at most 2.4 eta to be
    # considered a Jet in our analysis
    jet_mask = ((events.Jet.pt > 20.0) & (abs(events.Jet.eta) < 2.4))

    # require an object of the Jet collection to have at least 50 GeV pt and at most 2.4 eta
    jet_pt50_mask = ((events.Jet.pt > 50.0) & (abs(events.Jet.eta) < 2.4))

    # require an event to have at least two jets to be selected
    jet_sel = (ak.sum(jet_mask, axis=1) >= 2)

    # create the list of indices to be kept from the Jet collection using the jet_mask to create the
    # new Jet field containing only the selected Jet objects
    jet_indices = ak.local_index(events.Jet.pt)[jet_mask]

    # create the list of indices to be kept from the Jet collection using the jet_pt50_mask to create the
    # new Jet_pt50 field containing only the selected Jet_pt50 objects
    jet_pt50_indices = ak.local_index(events.Jet.pt)[jet_pt50_mask]

    return events, SelectionResult(
        steps={
            # boolean mask to create selection of the events with at least two jets, this will be
            # applied in the ReduceEvents task
            "jet": jet_sel,
        },
        objects={
            # in ReduceEvents, the Jet field will be replaced by the new Jet field containing only
            # selected jets, and a new field called Jet_pt50 containing the jets with pt higher than
            # 50 GeV will be created
            "Jet": {
                "Jet": jet_indices,
                "Jet_pt50": jet_pt50_indices,
            },
        },
        aux={
            # jet mask that lead to the jet_indices
            "jet_mask": jet_mask,
        },
    )


# Next, define an internal fatjet Selector to be used by the exposed Selector

@selector(
    # define some additional information here, e.g.
    # what columns are needed for this Selector?
    uses={
        "FatJet.pt",
    },
    # does this Selector produce any columns?
    produces=set(),

    # ...
)
def fatjet_selection_with_result(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    # require an object of the FatJet collection to have at least 40 GeV pt to be
    # considered a FatJet in our analysis
    fatjet_mask = (events.FatJet.pt > 40.0)

    # require an event to have at least one AK8-jet (=FatJet) to be selected
    fatjet_sel = (ak.sum(fatjet_mask, axis=1) >= 1)

    # create the list of indices to be kept from the FatJet collection using the fatjet_mask to create the
    # new FatJet field containing only the selected FatJet objects
    fatjet_indices = ak.local_index(events.FatJet.pt)[fatjet_mask]

    return events, SelectionResult(
        steps={
            # boolean mask to create selection of the events with at least two jets, this will be
            # applied in the ReduceEvents task
            "fatjet": fatjet_sel,
        },
        objects={
            # in ReduceEvents, the FatJet field will be replaced by the new FatJet field containing only
            # selected fatjets
            "FatJet": {
                "FatJet": fatjet_indices,
            },
        },
    )


# Next, define an internal lepton Selector that decides the channel of each event.
# `channel_id` is NOT a NanoAOD column: it is created here (1 = electron channel,
# 2 = muon channel, 0 = neither) and written into `events` so that downstream
# producers (e.g. `lepton_producer`) and categorizers (`cat_1e`, `cat_1m`) can use it.

@selector(
    uses={
        "Muon.pt", "Muon.eta",
        "Electron.pt", "Electron.eta",
    },
    produces={
        "channel_id",
    },
)
def lepton_selection(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    # simple muon / electron definitions (loose, for a first working version)
    muon_mask = (events.Muon.pt > 30.0) & (abs(events.Muon.eta) < 2.4)
    electron_mask = (events.Electron.pt > 35.0) & (abs(events.Electron.eta) < 2.5)

    n_muon = ak.sum(muon_mask, axis=1)
    n_electron = ak.sum(electron_mask, axis=1)

    # channel ids as defined in the analysis config (cfg.add_channel("e", id=1) / ("mu", id=2))
    ch_e = self.config_inst.get_channel("e").id
    ch_mu = self.config_inst.get_channel("mu").id

    # exactly one lepton of a single flavour -> assign that channel, otherwise 0
    channel_id = ak.zeros_like(events.event, dtype=np.int8)
    channel_id = ak.where((n_muon == 1) & (n_electron == 0), np.int8(ch_mu), channel_id)
    channel_id = ak.where((n_electron == 1) & (n_muon == 0), np.int8(ch_e), channel_id)

    # write the new column
    events = set_ak_column(events, "channel_id", channel_id)

    # indices of the selected leptons, kept for ReduceEvents
    muon_indices = ak.local_index(events.Muon.pt)[muon_mask]
    electron_indices = ak.local_index(events.Electron.pt)[electron_mask]

    return events, SelectionResult(
        steps={
            # require the event to fall into exactly one lepton channel
            "lepton": (channel_id != 0),
        },
        objects={
            "Muon": {"Muon": muon_indices},
            "Electron": {"Electron": electron_indices},
        },
        aux={
            "n_muon": n_muon,
            "n_electron": n_electron,
        },
    )


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
        # mc_weight, jet_selection_with_result, fatjet_selection_with_result, custom_increment_stats,
        mc_weight, jet_selection_with_result, lepton_selection, custom_increment_stats,
        process_ids,
        category_ids,
        lepton_producer
    },
    produces={
        mc_weight, lepton_selection, process_ids, category_ids, lepton_producer
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

    # add corrected mc weights to be used later for plotting and to calculate the sum saved in stats
    if self.dataset_inst.is_mc:
        events = self[mc_weight](events, **kwargs)

    # call the first internal selector, the jet selector, and save its result
    events, jet_results = self[jet_selection_with_result](events, **kwargs)
    results += jet_results

    # # call the second internal selector, the fatjet selector, and save its result
    # events, fatjet_results = self[fatjet_selection_with_result](events, **kwargs)
    # results += fatjet_results

    # lepton selection: decides the channel (writes the `channel_id` column)
    events, lepton_results = self[lepton_selection](events, **kwargs)
    results += lepton_results

    # merge Muon/Electron into a single `Lepton` collection based on `channel_id`
    events = self[lepton_producer](events, **kwargs)

    events = self[category_ids](events, results=results, **kwargs) # needs categories

    # combined event selection after all steps
    event_sel = reduce(and_, results.steps.values())
    results.event = event_sel

    # create process ids, used by custom_increment_stats
    events = self[process_ids](events, **kwargs)

    # use increment stats selector to update dictionary to be saved in json format
    events, results = self[custom_increment_stats](events, results, stats, **kwargs)

    return events, results