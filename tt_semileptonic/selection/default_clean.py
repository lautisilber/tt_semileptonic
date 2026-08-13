# coding: utf-8

# import the Selector class and the selector method
from columnflow.selection import Selector, selector

# also import the SelectionResult class
from columnflow.selection import SelectionResult
from columnflow.production.cms.mc_weight import mc_weight
from columnflow.production.processes import process_ids

# import the functions to combine the selection masks
from operator import and_
from functools import reduce

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import
ak = maybe_import("awkward")
np = maybe_import("numpy")

from collections import defaultdict, OrderedDict


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
    stats["num_events_selected"] += ak.sum(event_mask, axis=0)

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
        stats[f"sum_{name}"] += ak.sum(weights[mask])

        # sums per process id
        stats.setdefault(f"sum_{name}_per_process", defaultdict(float))
        for p in unique_process_ids:
            stats[f"sum_{name}_per_process"][int(p)] += ak.sum(
                weights[(events.process_id == p) & joinable_mask],
            )

    return events, results


# Now create the exposed Selector using the three above defined Selectors

@selector(
    # some information for Selector
    # e.g., if we want to use some internal Selector, make
    # sure that you have all the relevant information
    uses={
        # mc_weight, jet_selection_with_result, fatjet_selection_with_result, custom_increment_stats,
        mc_weight, jet_selection_with_result, custom_increment_stats,
        process_ids,
    },
    produces={
        mc_weight, process_ids,
    },

    # this is our top level Selector, so we need to make it reachable
    # for the SelectEvents task
    exposed=True,
)
def default_clean(
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

    # combined event selection after all steps
    event_sel = reduce(and_, results.steps.values())
    results.event = event_sel

    # create process ids, used by custom_increment_stats
    events = self[process_ids](events, **kwargs)

    # use increment stats selector to update dictionary to be saved in json format
    events, results = self[custom_increment_stats](events, results, stats, **kwargs)

    return events, results