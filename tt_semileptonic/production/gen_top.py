# coding: utf-8

"""
Gen-level top quark momenta and top-pt reweighting. Ported from mtt/production/gen_top.py
(only the pieces the weight chain needs -- ``gen_parton_top`` / ``top_pt_weight``; mttbar's
``gen_top_decay_products`` is unused here).
"""

from columnflow.production import Producer, producer
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column

ak = maybe_import("awkward")
np = maybe_import("numpy")


@producer(
    uses={
        "GenPart.pt", "GenPart.eta", "GenPart.phi", "GenPart.mass",
        "GenPart.pdgId", "GenPart.statusFlags",
    },
    produces={
        "GenPartonTop.pt", "GenPartonTop.eta", "GenPartonTop.phi",
        "GenPartonTop.mass", "GenPartonTop.pdgId",
    },
)
def gen_parton_top(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    Parton-level top quarks (before showering/hadronization), read by ``top_pt_weight``.
    """
    abs_id = abs(events.GenPart.pdgId)
    t = events.GenPart[abs_id == 6]
    t = t[t.hasFlags("isLastCopy")]
    t = t[~ak.is_none(t, axis=1)]

    events = set_ak_column(events, "GenPartonTop", t)
    return events


@gen_parton_top.skip
def gen_parton_top_skip(self: Producer) -> bool:
    # only meaningful for MC events that actually contain a top quark
    if not getattr(self, "dataset_inst", None):
        return False
    return self.dataset_inst.is_data or not self.dataset_inst.has_tag("has_top")


@producer(
    uses={"GenPartonTop.pt"},
    produces={"top_pt_weight", "top_pt_weight_up", "top_pt_weight_down"},
)
def top_pt_weight(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    ttbar top-pt reweighting: ``w = sqrt(SF(pt_t) * SF(pt_tbar))`` with
    ``SF(pt) = exp(a + b*pt)``, ``a``/``b`` from ``cfg.x.top_pt_reweighting_params``
    (TWiki TOP-16-008 recipe, values are the Run 2 ones -- TODO: update to Run 3 once
    available, see the ``chi2_parameters`` TODO in config_helper.py for the same caveat).
    Only valid for ttbar MC (``is_ttbar`` tag).
    """
    if not self.dataset_inst.has_tag("is_ttbar"):
        raise Exception(f"top_pt_weight should only run for ttbar datasets, got {self.dataset_inst}")

    params = self.config_inst.x.top_pt_reweighting_params

    # recipe caps the SF input at pt = 500 GeV
    pt_clamped = ak.where(events.GenPartonTop.pt > 500.0, 500.0, events.GenPartonTop.pt)
    sf = ak.pad_none(np.exp(params["a"] + params["b"] * pt_clamped), 2)

    # product of the SF for the top and the anti-top
    weight = np.sqrt(sf[:, 0] * sf[:, 1])

    # the recipe has no official uncertainty; +-50% is the common ad-hoc choice used by mttbar
    events = set_ak_column(events, "top_pt_weight", ak.fill_none(weight, 1.0))
    events = set_ak_column(events, "top_pt_weight_up", ak.fill_none(weight * 1.5, 1.0))
    events = set_ak_column(events, "top_pt_weight_down", ak.fill_none(weight * 0.5, 1.0))

    return events


@top_pt_weight.skip
def top_pt_weight_skip(self: Producer) -> bool:
    if not getattr(self, "dataset_inst", None):
        return False
    return self.dataset_inst.is_data or not self.dataset_inst.has_tag("is_ttbar")
