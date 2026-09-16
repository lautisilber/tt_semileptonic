# coding: utf-8

"""
AK8 (fat) jet top tagging and the all-hadronic veto.
Ported from mtt/selection/jets.py::top_tagged_jets.
"""

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult
from columnflow.columnar_util import sorted_indices_from_mask
from columnflow.production.cms.jet import fatjet_id

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")


@selector(
    uses={
        "event",
        "Lepton.pt", "Lepton.eta", "Lepton.phi", "Lepton.mass",
    },  # FatJet.{...} added in the init from the config
)
def top_tagged_jets(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    """
    AK8 top tagging (GloParT-v3 top-vs-QCD) and the all-hadronic veto: reject events with
    >= 2 top-tagged AK8 jets (``pt > 400``, ``|eta| < 2.5``, softdrop mass in
    ``[105, 210]``, tagger score above the working point, tight jet ID). Reads
    ``cfg.x.jet_selection.ak8``. Must run after ``lepton_producer`` (reads ``Lepton``).

    The tight fat-jet ID is recomputed rather than read from NanoAOD, for the same reason
    as the AK4 jet ID in ``selection/jets.py``: see ``columnflow.production.cms.jet.jet_id``
    (``fatjet_id`` is its ``FatJet``-derived variant).
    """
    p = self.config_inst.x.jet_selection.ak8
    fatjet = events[p.column]

    # recompute the fat-jet ID from the JME correctionlib file (cfg.x.fatjet_id / external
    # "jet_id" file) instead of trusting the (buggy) stored NanoAOD FatJet.jetId bitmap
    events = self[fatjet_id](events, **kwargs)
    # bit 2 = "Tight" working point, see JetIdConfig in cfg.x.fatjet_id
    tight_fatjet_id = (events.FatJet.jetId & 2 == 2)

    # top-vs-QCD score from the three GloParT-v3 categories (guard the 0/0 case)
    tqq, tq, qcd = (fatjet[c] for c in p.toptagger.column)
    denom = tqq + tq + qcd
    top_score = ak.where(denom > 0.0, (tqq + tq) / ak.where(denom > 0.0, denom, 1.0), 0.0)
    toptag = (top_score > p.toptagger.wp)

    # AK8 jets: pt > 200, |eta| < 2.5
    fatjet_mask = (fatjet.pt > p.min_pt.baseline) & (abs(fatjet.eta) < p.max_abseta)
    fatjet_indices = sorted_indices_from_mask(fatjet_mask, fatjet.pt, ascending=False)

    # top-tagged AK8 jets: harder pt, tagger WP, softdrop mass window, tight jet ID
    toptag_mask = (
        (fatjet.pt > p.min_pt.toptagged) &
        (abs(fatjet.eta) < p.max_abseta) &
        toptag &
        (fatjet.msoftdrop > p.msoftdrop[0]) &
        (fatjet.msoftdrop < p.msoftdrop[1]) &
        tight_fatjet_id
    )
    toptag_indices = sorted_indices_from_mask(toptag_mask, fatjet.pt, ascending=False)

    # all-hadronic veto: at most one top-tagged AK8 jet in the event
    all_had_veto = (ak.sum(toptag_mask, axis=-1) < 2)

    # top-tagged AK8 jets separated from the main lepton (for the boosted category later)
    delta_r_lepton = ak.firsts(fatjet.metric_table(events["Lepton"]), axis=-1)
    toptag_dr_lepton_mask = toptag_mask & ak.fill_none(delta_r_lepton > p.delta_r_lep, True)
    toptag_dr_lepton_indices = sorted_indices_from_mask(toptag_dr_lepton_mask, fatjet.pt, ascending=False)

    return events, SelectionResult(
        steps={
            "all_had_veto": all_had_veto,
        },
        objects={
            "FatJet": {
                "FatJet": fatjet_indices,
                "FatJetTopTag": toptag_indices,
                "FatJetTopTagDeltaRLepton": toptag_dr_lepton_indices,
            },
        },
        aux={
            "n_toptag": ak.sum(toptag_mask, axis=1),
            "n_toptag_delta_r_lepton": ak.sum(toptag_dr_lepton_mask, axis=1),
        },
    )


@top_tagged_jets.init
def top_tagged_jets_init(self: Selector) -> None:
    # the tagger score branch names come from the config, so declare columns here
    if not getattr(self, "config_inst", None):
        return
    p = self.config_inst.x.jet_selection.ak8
    cols = {"pt", "eta", "phi", "mass", "msoftdrop", *p.toptagger.column}
    self.uses |= {f"{p.column}.{c}" for c in cols}
    # fatjet_id recomputes FatJet.jetId from correctionlib; declare it as both a dependency
    # (uses) and something this selector's output now provides (produces)
    self.uses |= {fatjet_id}
    self.produces |= {fatjet_id}
