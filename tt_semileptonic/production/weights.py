# coding: utf-8

"""
Main event weight producer, combining the individual per-correction weight producers into
the columns named in ``cfg.x.event_weights`` (config_helper.py). Ported from
mtt/production/weights.py, trimmed to what's actually configured for this analysis (no
V+jets k-factor / top-tagging SF / L1 prefiring -- those have no config counterpart here
yet, see mttbar for the pattern if/when they're added).

Runs in ``cf.ProduceColumns`` (``--producers default``), i.e. after ``cf.ReduceEvents`` --
distinct from ``mc_weight``, which tt_semileptonic already computes earlier, inside the
``default`` *selector* (``selection/default.py``).
"""

from columnflow.production import Producer, producer
from columnflow.production.cms.electron import electron_weights
from columnflow.production.cms.muon import muon_weights
from columnflow.production.cms.pileup import pu_weight
from columnflow.production.normalization import normalization_weights
from columnflow.util import maybe_import

from tt_semileptonic.production.btag import upart_btag_weights
from tt_semileptonic.production.gen_top import gen_parton_top, top_pt_weight

ak = maybe_import("awkward")


@producer
def weights(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    Computes, for MC only: electron/muon scale factors, pileup weight, the b-tag scale
    factor (see ``production/btag.py``), the normalization weight, and -- for SM ttbar
    datasets -- the top-pt reweighting.
    """
    if self.dataset_inst.is_mc:
        # electron/muon SF phase space (pt/eta ranges the correctionlib SF is valid for);
        # values follow mttbar's 2024 config, since that's the only year configured here
        electron_mask = (events.Electron.pt >= 20.0) & (events.Electron.pt < 1000.0)
        events = self[electron_weights](events, electron_mask=electron_mask, **kwargs)

        muon_mask = (events.Muon.pt >= 30.0) & (abs(events.Muon.eta) < 2.4)
        events = self[muon_weights](events, muon_mask=muon_mask, **kwargs)

        # b-tag SF: jet phase space follows mttbar's 2024 config
        jet_mask = (events.Jet.pt >= 100.0) & (abs(events.Jet.eta) < 2.5)
        events = self[upart_btag_weights](events, jet_mask=jet_mask, **kwargs)

        events = self[pu_weight](events, **kwargs)

        # needs sum_mc_weight_per_process / num_events_per_process, already written by
        # selection/default.py::custom_increment_stats
        events = self[normalization_weights](events, **kwargs)

        if self.dataset_inst.has_tag("is_ttbar"):
            events = self[gen_parton_top](events, **kwargs)
            events = self[top_pt_weight](events, **kwargs)

    return events


@weights.init
def weights_init(self: Producer) -> None:
    if not getattr(self, "dataset_inst", None) or not self.dataset_inst.is_mc:
        return

    self.uses |= {
        electron_weights, muon_weights, upart_btag_weights, pu_weight, normalization_weights,
        "Electron.{pt,eta,phi,mass,deltaEtaSC}", "Muon.{pt,eta,phi,mass}",
    }
    self.produces |= {
        electron_weights, muon_weights, upart_btag_weights, pu_weight, normalization_weights,
    }

    if self.dataset_inst.has_tag("is_ttbar"):
        self.uses |= {gen_parton_top, top_pt_weight}
        self.produces |= {gen_parton_top, top_pt_weight}
