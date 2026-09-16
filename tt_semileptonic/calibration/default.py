# coding: utf-8

"""
Calibration methods.
"""

from columnflow.calibration import Calibrator, calibrator
# TODO should we add these later?
# from columnflow.calibration.cms.egamma import electron_scale_smear
# from columnflow.calibration.cms.muon import muon_sr
from columnflow.production.cms.mc_weight import mc_weight
from columnflow.production.cms.seeds import deterministic_seeds
from columnflow.util import maybe_import

from tt_semileptonic.calibration.jets import jet_energy, jet_lepton_cleaner

ak = maybe_import("awkward")


@calibrator(
    uses={mc_weight, deterministic_seeds, jet_lepton_cleaner, jet_energy},
    produces={mc_weight, deterministic_seeds, jet_lepton_cleaner, jet_energy},
)
def default(self: Calibrator, events: ak.Array, **kwargs) -> ak.Array:
    if self.dataset_inst.is_mc:
        # Stores the mc_weight in events
        events = self[mc_weight](events, **kwargs)

    # Produces deterministic event or jet seeds and stores them in events
    events = self[deterministic_seeds](events, **kwargs)

    # subtract clustered-lepton contamination from jet 4-vectors, then apply JEC (+ JER on MC)
    events = self[jet_lepton_cleaner](events, **kwargs)
    events = self[jet_energy](events, **kwargs)

    return events
