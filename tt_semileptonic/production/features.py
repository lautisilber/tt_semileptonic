# coding: utf-8

"""
Higher-level event features: multiplicities/HT, dijet kinematics, jet-lepton kinematics.
Ported from mtt/production/features.py, trimmed to what's self-contained here -- mttbar's
``jet_lepton_features`` recomputes the main lepton via its own ``choose_lepton``, but we
already have the equivalent ``Lepton`` column (``production/lepton.py::lepton_producer``,
computed in ``selection/default.py`` and kept post-``ReduceEvents``), so this reads that
directly instead. mttbar's ``jet_energy_shifts`` pseudo-producer (registers JEC/JER shift
names on the producer) is left out -- our JEC/JER calibrators currently only run nominal
(``uncertainty_sources: []``, see ``calibration/jets.py``), so there's nothing yet for it
to register.
"""

from columnflow.production import Producer, producer
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column, EMPTY_FLOAT

ak = maybe_import("awkward")
coffea = maybe_import("coffea")
maybe_import("coffea.nanoevents.methods.nanoaod")


@producer(
    uses={"Jet.{pt,eta,phi,mass}"},
    produces={"dijet_mass", "dijet_delta_r"},
)
def jj_features(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """Invariant mass and delta-R of the two leading AK4 jets."""
    events = ak.Array(events, behavior=coffea.nanoevents.methods.nanoaod.behavior)
    events["Jet"] = ak.with_name(events.Jet, "PtEtaPhiMLorentzVector")

    # pad with None so events with fewer than 2 jets don't raise on indexing
    jets = ak.pad_none(events.Jet, 2)

    dijet_mass = (jets[:, 0] + jets[:, 1]).mass
    dijet_delta_r = jets[:, 0].delta_r(jets[:, 1])

    events = set_ak_column(events, "dijet_mass", ak.fill_none(dijet_mass, EMPTY_FLOAT))
    events = set_ak_column(events, "dijet_delta_r", ak.fill_none(dijet_delta_r, EMPTY_FLOAT))

    return events


@producer(
    uses={
        "Lepton.{pt,eta,phi,mass}",
        "Jet.{pt,eta,phi,mass}",
    },
    produces={"jet_lep_pt_rel", "jet_lep_delta_r"},
)
def jet_lepton_features(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """pTrel and delta-R of the event's lepton relative to its closest AK4 jet (pt > 15)."""
    events = ak.Array(events, behavior=coffea.nanoevents.methods.nanoaod.behavior)
    events["Jet"] = ak.with_name(events.Jet, "PtEtaPhiMLorentzVector")
    events["Lepton"] = ak.with_name(events.Lepton, "PtEtaPhiMLorentzVector")

    jets = events.Jet[events.Jet.pt > 15]
    lepton = events.Lepton

    # closest jet to the lepton by delta-R
    lepton_jet_deltar = ak.firsts(jets.metric_table(lepton), axis=-1)
    idx_closest = ak.argmin(lepton_jet_deltar, axis=1, keepdims=True)
    lepton_closest_jet = ak.firsts(jets[idx_closest])

    # convert to 3D vectors for the cross product (pTrel definition)
    lepton_3d = lepton.to_Vector3D()
    lepton_closest_jet_3d = lepton_closest_jet.to_Vector3D()
    jet_lep_pt_rel = lepton_3d.cross(lepton_closest_jet_3d).p / lepton_closest_jet.p
    jet_lep_delta_r = lepton_closest_jet.delta_r(lepton)

    events = set_ak_column(events, "jet_lep_pt_rel", ak.fill_none(jet_lep_pt_rel, EMPTY_FLOAT))
    events = set_ak_column(events, "jet_lep_delta_r", ak.fill_none(jet_lep_delta_r, EMPTY_FLOAT))

    return events


@producer(
    uses={
        jj_features, jet_lepton_features,
        "Jet.pt", "FatJet.pt", "Muon.pt", "Electron.pt",
    },
    produces={
        jj_features, jet_lepton_features,
        "ht", "n_jet", "n_fatjet", "n_muon", "n_electron",
    },
)
def features(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """All high-level features: scalar jet pt sum (ht), object multiplicities, dijet and jet-lepton kinematics."""
    # `ak.num` on a vector-behavior array with missing LV fields can raise, so strip
    # parameters before counting (mirrors mtt/production/features.py)
    jet = ak.without_parameters(events.Jet)
    fatjet = ak.without_parameters(events.FatJet)
    muon = ak.without_parameters(events.Muon)
    electron = ak.without_parameters(events.Electron)

    events = set_ak_column(events, "n_jet", ak.num(jet.pt, axis=-1))
    events = set_ak_column(events, "n_fatjet", ak.num(fatjet.pt, axis=-1))
    events = set_ak_column(events, "n_muon", ak.num(muon.pt, axis=-1))
    events = set_ak_column(events, "n_electron", ak.num(electron.pt, axis=-1))
    events = set_ak_column(events, "ht", ak.sum(jet.pt, axis=-1))

    events = self[jj_features](events, **kwargs)
    events = self[jet_lepton_features](events, **kwargs)

    return events
