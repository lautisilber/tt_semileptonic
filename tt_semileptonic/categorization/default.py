# coding: utf-8

"""
Exemplary selection methods.
"""

from columnflow.categorization import Categorizer, categorizer
from columnflow.columnar_util import Route
from columnflow.util import maybe_import

ak = maybe_import("awkward")


#
# categorizer functions used by categories definitions
#

@categorizer(uses={"event"})
def cat_incl(self: Categorizer, events: ak.Array, **kwargs) -> tuple[ak.Array, ak.Array]:
    """Passes every event."""
    # fully inclusive selection
    return events, ak.ones_like(events.event, dtype=bool)

@categorizer(uses={"event", "channel_id"})
def cat_1m(self: Categorizer, events: ak.Array, **kwargs) -> tuple[ak.Array, ak.Array]:
    """Select only events in the muon channel."""
    ch = self.config_inst.get_channel("mu")
    mask = events["channel_id"] == ch.id
    return events, mask

@categorizer(uses={"event", "channel_id"})
def cat_1e(self: Categorizer, events: ak.Array, **kwargs) -> ak.Array:
    """Select only events in the electron channel."""
    ch = self.config_inst.get_channel("e")
    mask = events["channel_id"] == ch.id
    return events, mask

@categorizer(uses={"cutflow.n_toptag_delta_r_lepton"})
def cat_0t(self: Categorizer, events: ak.Array, **kwargs) -> ak.Array:
    """Select only events with zero top-tagged fat jets."""
    mask = (Route("cutflow.n_toptag_delta_r_lepton").apply(events) == 0)
    return events, mask

@categorizer(uses={"cutflow.n_toptag_delta_r_lepton"})
def cat_1t(self: Categorizer, events: ak.Array, **kwargs) -> ak.Array:
    """Select only events with exactly one top-tagged fat jet."""
    mask = (Route("cutflow.n_toptag_delta_r_lepton").apply(events) == 1)
    return events, mask
