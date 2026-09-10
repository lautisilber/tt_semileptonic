# coding: utf-8

"""
Lepton-jet 2D cut, ported from mtt/selection/jets.py::lepton_jet_2d_selection.
"""

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")

from tt_semileptonic.production.lepton import selected_lepton_jet_mask, lepton_jet_match_columns


@selector(
    uses={
        "event", "channel_id", "pt_regime",
        "Jet.pt", "Jet.eta", "Jet.phi", "Jet.mass",
        "Muon.pt", "Muon.eta", "Muon.phi", "Muon.mass",
        "Electron.pt", "Electron.eta", "Electron.phi", "Electron.mass",
        *lepton_jet_match_columns,
    },
)
def lepton_jet_2d_selection(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    """
    2D requirement, replacing the isolation cut for high-pt leptons:

        delta_r(lepton, closest jet) > 0.4   OR   pt_rel(lepton, jet) > 25 GeV

    where ``pt_rel`` is the magnitude of the lepton momentum perpendicular to the jet
    axis (``|p_lep x p_jet| / |p_jet|``). Only applied in the high-pt regime
    (``pt_regime == 2``) -- low-pt leptons already carry isolation in their ID. Jets are
    ``pt > 15`` and lepton-cleaned. Reads ``cfg.x.lepton_jet_iso``.

    Relies on the NanoAOD (vector) behavior the events are already read with
    (``metric_table`` / ``to_Vector3D``) -- no explicit ``attach_coffea_behavior``.
    """
    p = self.config_inst.x.lepton_jet_iso
    ch_e = self.config_inst.get_channel("e")
    ch_mu = self.config_inst.get_channel("mu")

    # jets for the 2D cut: pt > 15, not the selected lepton's own PF jet
    jets = events.Jet[(events.Jet.pt > p.min_pt) & ~selected_lepton_jet_mask(events)]

    sel = ak.ones_like(events.event, dtype=bool)
    for ch, route in [(ch_e, "Electron"), (ch_mu, "Muon")]:
        coll = events[route]
        pass_lepton = coll[coll.pass_lepton]

        # nothing to do if this chunk has no selected lepton of this flavour
        if ak.sum(ak.num(pass_lepton, axis=1)) == 0:
            continue

        lepton = ak.firsts(pass_lepton, axis=1)

        # delta_r of the (single) selected lepton to every 2D-cut jet, and the closest one
        delta_r = ak.firsts(jets.metric_table(lepton), axis=-1)
        closest_jet = ak.firsts(jets[ak.argmin(delta_r, axis=-1, keepdims=True)], axis=1)

        far = ak.fill_none(ak.all(delta_r > p.min_delta_r, axis=-1), True)

        lepton_3d = lepton.to_Vector3D()
        jet_3d = closest_jet.to_Vector3D()
        pt_rel = lepton_3d.cross(jet_3d).p / jet_3d.p
        ch_sel = ak.where(ak.fill_none(pt_rel > p.min_pt_rel, False), True, far)

        sel = ak.where(events.channel_id == ch.id, ch_sel, sel)

    # only relevant for high-pt leptons; pass everything else through
    sel = ak.where(events.pt_regime == 2, sel, True)
    sel = ak.fill_none(sel, True)

    return events, SelectionResult(steps={"lepton_jet_2d": sel})
