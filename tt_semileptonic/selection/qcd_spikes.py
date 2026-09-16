# coding: utf-8

"""
Selection reducing spiking QCD behavior. Ported from mtt/selection/qcd_spikes.py.
"""

from columnflow.util import maybe_import

from columnflow.selection import Selector, SelectionResult, selector

np = maybe_import("numpy")
ak = maybe_import("awkward")


@selector(
    uses={
        "Jet.pt",
        "LHE.HT",
    },
)
def qcd_spikes(
    self: Selector,
    events: ak.Array,
    **kwargs,
) -> tuple[ak.Array, SelectionResult]:
    """
    Only meant for QCD MC (gated on the ``is_qcd`` dataset tag in ``selection/default.py``,
    which is inherently MC-only). HT-binned QCD samples are prone to a mismeasurement
    pathology where a single jet is reconstructed with far more pt than the generator-level
    hard-scatter energy scale (``LHE.HT``) can account for -- an unphysical "spike". Rejects
    events where the leading jet's pt exceeds the event's ``LHE.HT``, since a genuine jet
    cannot carry more transverse energy than was generated in the hard process.
    """
    sel_jets = ak.fill_none(events.LHE.HT > ak.firsts(events.Jet.pt), True)

    # build and return selection results
    return events, SelectionResult(
        steps={
            "QCDSpikes": sel_jets,
        },
    )
