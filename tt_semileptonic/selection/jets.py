# coding: utf-8

"""
Selection involving AK4 jets, ported from mtt/selection/jets.py::jet_selection.
"""

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult
from columnflow.columnar_util import sorted_indices_from_mask

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")
np = maybe_import("numpy")

from tt_semileptonic.production.lepton import selected_lepton_jet_mask, lepton_jet_match_columns


@selector(
    uses={"channel_id"},  # Jet.{...} + lepton-match columns added in the init
)
def jet_selection(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    """
    Baseline AK4 jet selection. Reads ``cfg.x.jet_selection.ak4``. Runs after the lepton
    selection: the selected lepton's own PF jet is removed via ``selected_lepton_jet_mask``
    (NanoAOD clusters an isolated lepton into a jet, which would otherwise be counted).

    TODO: the tight jet ID is not applied yet -- ``Jet.jetId`` is not stored in 2024
    NanoAOD v15, it has to be recomputed with ``columnflow.production.cms.jet.jet_id``,
    which needs the JME jet-id correction file (add when the correction infrastructure
    is set up).
    """
    sel_params = self.config_inst.x.jet_selection.ak4
    jet = events[sel_params.column]

    ch_e = self.config_inst.get_channel("e")
    ch_mu = self.config_inst.get_channel("mu")
    el_id = (events.channel_id == ch_e.id)
    mu_id = (events.channel_id == ch_mu.id)

    # jets that are actually the selected lepton -> excluded from every jet collection
    not_lepton = ~selected_lepton_jet_mask(events)

    # loose jets (pt > 0.1) -- keeps every real jet, filters out cleaned/degenerate ones
    loose_jet_mask = not_lepton & (jet.pt > 0.1)
    loose_jet_indices = sorted_indices_from_mask(loose_jet_mask, jet.pt, ascending=False)

    # baseline jets: pt > 30, |eta| < 2.5
    jet_mask = (
        not_lepton &
        (abs(jet.eta) < sel_params.max_abseta) &
        (jet.pt > sel_params.min_pt.baseline)
    )
    jet_indices = sorted_indices_from_mask(jet_mask, jet.pt, ascending=False)

    # >= 2 baseline jets with channel-dependent leading / subleading pt thresholds
    leading_jets = ak.pad_none(jet[jet_indices], 2)
    el_jet_sel = ak.fill_none(
        (leading_jets[:, 0].pt > sel_params.min_pt.e[0]) &
        (leading_jets[:, 1].pt > sel_params.min_pt.e[1]),
        False,
    )
    mu_jet_sel = ak.fill_none(
        (leading_jets[:, 0].pt > sel_params.min_pt.mu[0]) &
        (leading_jets[:, 1].pt > sel_params.min_pt.mu[1]),
        False,
    )
    sel_jet = (el_id & el_jet_sel) | (mu_id & mu_jet_sel)

    # b tagging (UParT AK4 discriminant, medium WP), applied on the baseline jets
    btag = jet[sel_params.btagger.column]
    bjet_mask = jet_mask & (btag >= sel_params.btagger.wp)
    lightjet_mask = jet_mask & (btag < sel_params.btagger.wp)
    sel_bjet = (ak.sum(bjet_mask, axis=-1) >= 1)

    bjet_indices = sorted_indices_from_mask(bjet_mask, jet.pt, ascending=False)
    lightjet_indices = sorted_indices_from_mask(lightjet_mask, jet.pt, ascending=False)

    return events, SelectionResult(
        steps={
            "jet": sel_jet,
            "bjet": sel_bjet,
        },
        objects={
            "Jet": {
                "LooseJet": loose_jet_indices,
                "Jet": jet_indices,
                "BJet": bjet_indices,
                "LightJet": lightjet_indices,
            },
        },
        aux={
            "n_jet": ak.sum(jet_mask, axis=1),
            "n_bjet": ak.sum(bjet_mask, axis=1),
        },
    )


@jet_selection.init
def jet_selection_init(self: Selector) -> None:
    # the b-tagger branch name comes from the config, so declare columns here.
    # pt/eta/phi/mass are all requested even though only pt/eta are cut on: the events
    # are read with NanoAOD (vector) behavior, so `events.Jet.pt` only works when the
    # full Lorentz-vector fields are present (columnflow convention).
    if not getattr(self, "config_inst", None):
        return
    p = self.config_inst.x.jet_selection.ak4
    self.uses |= {
        f"{p.column}.{c}" for c in ("pt", "eta", "phi", "mass", p.btagger.column)
    }
    self.uses |= lepton_jet_match_columns
