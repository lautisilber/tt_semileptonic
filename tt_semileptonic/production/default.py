# coding: utf-8

"""
Top-level default producer, run via ``--producers default`` in ``cf.ProduceColumns``.
Currently just wraps ``weights``; extend here once other producers (features, ttbar
reconstruction, ...) exist, mirroring mtt/production/default.py.
"""

from columnflow.production import Producer, producer
from columnflow.util import maybe_import

from tt_semileptonic.production.weights import weights

ak = maybe_import("awkward")


@producer(
    uses={weights},
    produces={weights},
)
def default(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    events = self[weights](events, **kwargs)
    return events
