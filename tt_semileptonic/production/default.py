# coding: utf-8

"""
Top-level default producer, run via ``--producers default`` in ``cf.ProduceColumns``.
Wraps ``weights`` and ``features``; extend here once other producers (ttbar
reconstruction, ...) exist, mirroring mtt/production/default.py.
"""

from columnflow.production import Producer, producer
from columnflow.util import maybe_import

from tt_semileptonic.production.weights import weights
from tt_semileptonic.production.features import features

ak = maybe_import("awkward")


@producer(
    uses={weights, features},
    produces={weights, features},
)
def default(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    events = self[weights](events, **kwargs)
    events = self[features](events, **kwargs)
    return events
