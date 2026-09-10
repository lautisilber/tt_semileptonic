# coding: utf-8

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult
from columnflow.columnar_util import sorted_indices_from_mask

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")

from tt_semileptonic.production.lepton import lepton_definition


# Internal lepton Selector. It decides nothing itself: `lepton_definition`
# (tt_semileptonic.production.lepton) writes the pass_lepton / pass_veto_lepton masks,
# `channel_id` and `pt_regime`; here those become a selection step, the selected object
# collections for ReduceEvents, and lepton-multiplicity aux info.

@selector(
    uses={
        lepton_definition,
        "Muon.pt", "Electron.pt",
    },
    produces={
        lepton_definition,
    },
)
def lepton_selection(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    # write Muon/Electron pass_lepton + pass_veto_lepton, channel_id, pt_regime
    events = self[lepton_definition](events, **kwargs)

    # pt-sorted index lists (descending) for ReduceEvents
    muon_idx = sorted_indices_from_mask(events.Muon.pass_lepton, events.Muon.pt, ascending=False)
    electron_idx = sorted_indices_from_mask(events.Electron.pass_lepton, events.Electron.pt, ascending=False)
    veto_muon_idx = sorted_indices_from_mask(events.Muon.pass_veto_lepton, events.Muon.pt, ascending=False)
    veto_electron_idx = sorted_indices_from_mask(events.Electron.pass_veto_lepton, events.Electron.pt, ascending=False)

    n_tight = ak.num(muon_idx, axis=1) + ak.num(electron_idx, axis=1)
    n_veto = ak.num(veto_muon_idx, axis=1) + ak.num(veto_electron_idx, axis=1)

    return events, SelectionResult(
        steps={
            # exactly one signal lepton, in exactly one channel
            "lepton": (events.channel_id != 0),
            # no additional (signal or veto) lepton in the event
            "dilepton_veto": ((n_tight + n_veto) <= 1),
        },
        objects={
            "Muon": {"Muon": muon_idx, "VetoMuon": veto_muon_idx},
            "Electron": {"Electron": electron_idx, "VetoElectron": veto_electron_idx},
        },
        aux={
            "pt_regime": events.pt_regime,
            "n_muon": ak.num(muon_idx, axis=1),
            "n_electron": ak.num(electron_idx, axis=1),
        },
    )
