# coding: utf-8

"""
Selection on missing transverse momentum, ported from mtt/selection/jets.py::met_selection.
"""

from columnflow.selection import Selector, selector
from columnflow.selection import SelectionResult

# maybe import awkward in case this Selector is actually run, this needs to be set as columnflow
# would else give an error during setup, as these packages are not in the default sandbox
from columnflow.util import maybe_import

ak = maybe_import("awkward")


@selector(
    uses={"channel_id"},  # <met column>.{pt,phi} added in the init from the config
)
def met_selection(self: Selector, events: ak.Array, **kwargs) -> tuple[ak.Array, SelectionResult]:
    """
    Channel-dependent missing transverse momentum cut, from ``cfg.x.met_selection``
    (``PuppiMET.pt`` above 60 GeV in the e channel, 70 GeV in the mu channel).
    Depends on ``channel_id`` -> must run after the lepton selection.
    """
    p = self.config_inst.x.met_selection
    met_pt = events[p.column].pt

    ch_e = self.config_inst.get_channel("e")
    ch_mu = self.config_inst.get_channel("mu")
    el_id = (events.channel_id == ch_e.id)
    mu_id = (events.channel_id == ch_mu.id)

    sel_met = (
        (el_id & (met_pt > p.min_pt.e)) |
        (mu_id & (met_pt > p.min_pt.mu))
    )
    sel_met = ak.fill_none(sel_met, False)

    return events, SelectionResult(
        steps={"met": sel_met},
    )


@met_selection.init
def met_selection_init(self: Selector) -> None:
    # the MET collection name comes from the config; request pt + phi so the NanoAOD
    # vector behavior on `events.<column>.pt` is valid
    if not getattr(self, "config_inst", None):
        return
    column = self.config_inst.x.met_selection.column
    self.uses |= {f"{column}.pt", f"{column}.phi"}
