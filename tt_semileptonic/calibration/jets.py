# coding: utf-8

"""
Jet energy calibration: lepton-cleaning of jet 4-vectors, then JEC + JER (nominal only for
now). Ported from mtt/calibration/jets.py.
"""

from columnflow.calibration import Calibrator, calibrator
from columnflow.calibration.cms.jets import jec_ak4, jer_ak4, jec_ak8, jer_ak8
from columnflow.util import maybe_import
from columnflow.production.util import attach_coffea_behavior, lv_xyzt, lv_mass
from columnflow.columnar_util import set_ak_column

ak = maybe_import("awkward")
np = maybe_import("numpy")


# nominal-only JEC/JER derivatives: the analysis MET is PuppiMET, not the NanoAOD default
# MET/RawMET the stock jec_ak4/jer_ak4 assume, and shifted (non-nominal) uncertainty sources
# are deferred (see CHANGES.md) so the produced-columns surface stays small while this is
# validated end to end.
jec_ak4_nominal = jec_ak4.derive(
    "jec_ak4_nominal",
    cls_dict={
        "uncertainty_sources": [],
        "met_name": "PuppiMET",
        "raw_met_name": "RawPuppiMET",
    },
)
jer_ak4_nominal = jer_ak4.derive(
    "jer_ak4_nominal",
    cls_dict={
        "jec_uncertainty_sources": [],
        "met_name": "PuppiMET",
        "raw_met_name": "RawPuppiMET",
    },
)

# MET propagation disabled for AK8: already handled by the AK4 calibrators above
jec_ak8_nominal = jec_ak8.derive(
    "jec_ak8_nominal",
    cls_dict={
        "uncertainty_sources": [],
        "propagate_met": False,
        "met_name": "DO_NOT_USE",
        "raw_met_name": "DO_NOT_USE",
    },
)
jer_ak8_nominal = jer_ak8.derive(
    "jer_ak8_nominal",
    cls_dict={
        "jec_uncertainty_sources": [],
        "propagate_met": False,
        "met_name": "DO_NOT_USE",
        "raw_met_name": "DO_NOT_USE",
    },
)


@calibrator
def jet_energy(self: Calibrator, events: ak.Array, **kwargs) -> ak.Array:
    """
    Common calibrator for jet energy corrections: nominal JEC for data, nominal JEC + JER for
    MC. AK4 fully before AK8 (AK8's own MET propagation is disabled; AK4 already handled it).
    Used/produced columns and dependent calibrators are declared in the init function below.
    """
    if self.dataset_inst.is_mc:
        events = self[jec_ak4_nominal](events, **kwargs)
        events = self[jer_ak4_nominal](events, **kwargs)
        events = self[jec_ak8_nominal](events, **kwargs)
        events = self[jer_ak8_nominal](events, **kwargs)
    else:
        events = self[jec_ak4_nominal](events, **kwargs)
        events = self[jec_ak8_nominal](events, **kwargs)

    return events


@jet_energy.init
def jet_energy_init(self: Calibrator) -> None:
    if getattr(self, "dataset_inst", None) and self.dataset_inst.is_mc:
        self.uses |= {jec_ak4_nominal, jer_ak4_nominal, jec_ak8_nominal, jer_ak8_nominal}
        self.produces |= {jec_ak4_nominal, jer_ak4_nominal, jec_ak8_nominal, jer_ak8_nominal}
    else:
        self.uses |= {jec_ak4_nominal, jec_ak8_nominal}
        self.produces |= {jec_ak4_nominal, jec_ak8_nominal}


@calibrator(
    uses={
        "Electron.pt", "Electron.eta", "Electron.phi", "Electron.mass",
        "Muon.pt", "Muon.eta", "Muon.phi", "Muon.mass",
        "Jet.pt", "Jet.eta", "Jet.phi", "Jet.mass", "Jet.rawFactor",
        # index of electrons/muons matched to jets
        "Jet.muonIdx1", "Jet.muonIdx2", "Jet.electronIdx1", "Jet.electronIdx2",
        # PF energy fractions
        "Jet.chEmEF", "Jet.muEF",
        attach_coffea_behavior,
    },
    produces={
        "Jet.pt", "Jet.eta", "Jet.phi", "Jet.mass", "Jet.rawFactor",
        "Jet.chEmEF", "Jet.muEF",
    },
)
def jet_lepton_cleaner(self: Calibrator, events: ak.Array, **kwargs) -> ak.Array:
    """
    Subtracts the 4-vector of any electron/muon clustered into a jet (matched via
    ``Jet.{muon,electron}Idx1/2``, i.e. *any* PF lepton, not just the one selected signal
    lepton) from that jet's 4-vector, before JEC/JER run. Complements the index-based
    overlap removal in ``production/lepton.py::selected_lepton_jet_mask`` (which only drops
    the selected lepton's own jet outright): this corrects jets that merely have some lepton
    energy clustered into them, relevant for boosted topologies where a lepton sits near but
    not on top of a genuine jet axis.

    Must run before JEC: reverts NanoAOD's own default jet energy correction first (using
    ``rawFactor``, then resetting it to 0), so JEC/JER afterward compute their corrections
    starting from the lepton-subtracted raw jet, not one already corrected at the
    (contaminated) pre-cleaning energy scale.
    """
    # load coffea behaviors for simplified arithmetic with vectors
    events["Electron"] = ak.with_name(events.Electron, "PtEtaPhiMLorentzVector")
    events["Muon"] = ak.with_name(events.Muon, "PtEtaPhiMLorentzVector")
    events["Jet"] = ak.with_name(events.Jet, "PtEtaPhiMLorentzVector")

    # revert JEC for jet pt and jet mass, set correction factor to 0
    events = set_ak_column(events, "Jet.pt", events.Jet.pt * (1 - events.Jet.rawFactor))
    events = set_ak_column(events, "Jet.mass", events.Jet.mass * (1 - events.Jet.rawFactor))
    events = set_ak_column(events, "Jet.rawFactor", 0)

    # build jet lorentz vectors
    jet_lv = lv_xyzt(events.Jet)

    # indices of leptons matched to each jet, None if no matched lepton
    idx_e1 = ak.mask(events.Jet.electronIdx1, events.Jet.electronIdx1 >= 0)
    idx_e2 = ak.mask(events.Jet.electronIdx2, events.Jet.electronIdx2 >= 0)
    idx_m1 = ak.mask(events.Jet.muonIdx1, events.Jet.muonIdx1 >= 0)
    idx_m2 = ak.mask(events.Jet.muonIdx2, events.Jet.muonIdx2 >= 0)

    # list with matched leptons
    jet_leptons_types = [
        (events.Electron[idx_e1], "e"),
        (events.Electron[idx_e2], "e"),
        (events.Muon[idx_m1], "mu"),
        (events.Muon[idx_m2], "mu"),
    ]

    # total energy from clustered leptonic PF candidates
    jet_pf_energies = {
        "mu": jet_lv.energy * events.Jet.muEF,
        "e": jet_lv.energy * events.Jet.chEmEF,
    }

    # subtract lepton contributions from jets
    tolerance = 0.1
    for jet_lepton, jet_lepton_type in jet_leptons_types:
        jet_lepton_lv = lv_xyzt(jet_lepton)
        jet_lv_cleaned = lv_xyzt(jet_lv - jet_lepton_lv)

        jet_pf_energy = jet_pf_energies[jet_lepton_type]
        jet_pf_energy_cleaned = jet_pf_energy - jet_lepton_lv.energy

        # only perform the cleaning of the current lepton if the following conditions are met

        # lepton energy compatible with PF energy fraction (within tolerance)
        lep_energy_pf_compatible = (jet_lepton_lv.energy < (1 + tolerance) * jet_pf_energy)

        # calculate square of cleaned jet mass
        jet_lv_cleaned_mass_sq = jet_lv_cleaned.energy**2 - jet_lv_cleaned.rho**2
        # mask values that would lead to imaginary masses, but substitute the absolute value
        # if the mass square is only negative within tolerance (likely a lepton fake)
        jet_lv_cleaned_mass = ak.mask(
            np.sqrt(abs(jet_lv_cleaned_mass_sq)),
            jet_lv_cleaned_mass_sq >= -tolerance,
        )

        # cleaning does not result in a negative/imaginary/undefined mass
        mass_stays_positive = ~ak.is_none(jet_lv_cleaned_mass, axis=1)

        # angle before/after cleaning is similar, or the cleaned jet is very low pt (likely a
        # pure lepton fake, where resolution effects can flip the angle's sign)
        angle_change_small = (
            (jet_lv.delta_r(jet_lv_cleaned) <= np.pi / 2) |
            (jet_lv_cleaned.pt < 10)
        )

        # AND of cleaning conditions; None (no matched lepton) -> no cleaning
        do_clean = mass_stays_positive & angle_change_small & lep_energy_pf_compatible
        do_clean = ak.fill_none(do_clean, False)

        # update jet LV
        jet_lv = ak.where(do_clean, jet_lv_cleaned, jet_lv)

        # update jet PF energies
        jet_pf_energies[jet_lepton_type] = ak.where(do_clean, jet_pf_energy_cleaned, jet_pf_energy)

    # save updated jet variables
    jet_lv = lv_mass(jet_lv)
    for var in ["pt", "eta", "phi", "mass"]:
        # ensure no non-finite values: a near-total lepton fake can clean a jet down to
        # ~zero momentum, where eta = -ln(tan(theta/2)) diverges to +-inf as the jet
        # approaches the beam axis -- ak.nan_to_none only catches NaN, not +-inf (mttbar's
        # original code used it regardless; harmless there only because mttbar's law.cfg
        # has check_finite_output: None, so it never checks for this). Mapping to 0 here is
        # fine physically, not just numerically: a jet whose pt was cleaned down to ~0 is
        # already a near-total lepton fake with no real jet left to describe, so its eta
        # carries no meaningful information regardless -- there is no "more correct" value.
        value = ak.nan_to_num(getattr(jet_lv, var), nan=0.0, posinf=0.0, neginf=0.0)
        value = ak.nan_to_num(getattr(jet_lv, var), nan=0.0, posinf=0.0, neginf=0.0)
        events = set_ak_column(events, f"Jet.{var}", value)

    return events
