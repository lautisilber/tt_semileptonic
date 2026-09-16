# coding: utf-8

"""
b-tag scale factor weight -- placeholder.

``columnflow.production.cms.btag.btag_weights`` (the stock producer, config already ready
at ``cfg.x.btag_sf`` / external file ``btag_sf_corr``) cannot be used as-is for our 2024
UParT working point: ``btag_weights_post_init`` (columnflow/production/cms/btag.py) always
overwrites ``self.btag_uncs`` with a hardcoded Run-2-era name set
(``hf``/``lf``/``hfstats1``/``hfstats2``/``lfstats1``/``lfstats2``/``cferr1``/``cferr2``),
running *after* `.derive()`, so it silently clobbers any ``cls_dict={"btag_uncs": ...}``
override -- the pattern mttbar's ``upart_btag_weights`` relies on. The actual 2024
``UParTAK4_kinfit`` correction set (in the already-fetched ``btagging_preliminary.json.gz``)
uses a different systematic-name set (``fsrdef``/``hdamp``/``isrdef``/``jer``/``jes``/
``mass``/``statistic``/``tune``), so calling ``btag_weights`` unmodified raises a
correctionlib lookup error the moment it evaluates e.g. ``up_hf``, which the file doesn't
have.

Proper fix (not done here): a derived producer that fully overrides ``.post_init`` (not
just the ``btag_uncs`` class attribute) to set the 2024-correct names, or a columnflow-side
fix upstream. Until then this stub keeps the rest of the weight chain runnable: it writes a
flat ``btag_weight = 1`` (no correction applied) and is *not* added to
``cfg.x.event_weights``, so it has zero effect on the combined event weight -- swap the
import in ``production/weights.py`` for the real producer once it exists.
"""

from columnflow.production import Producer, producer
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column

ak = maybe_import("awkward")
np = maybe_import("numpy")


@producer(
    uses={"event"},
    produces={"btag_weight"},
    mc_only=True,
)
def btag_weight_stub(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    """
    Placeholder for the real b-tag SF (see module docstring). Always ``1`` -- no correction.
    """
    events = set_ak_column(events, "btag_weight", ak.ones_like(events.event, dtype=np.float32))
    return events
