# coding: utf-8

"""
Top-level default producer, run via ``--producers default`` in ``cf.ProduceColumns``.
Wraps ``ttbar_reco`` (chi2 reconstruction), ``weights``, ``features``, and a final
``category_ids`` recompute -- the last one picks up the chi2/cos(theta*) categories,
extending the ``category_ids`` column ``cf.SelectEvents`` already wrote with the
channel/top-tag categories (mirrors mtt/production/default.py).
"""

from columnflow.production import Producer, producer
from columnflow.production.categories import category_ids
from columnflow.util import maybe_import

from tt_semileptonic.production.ttbar_reco import ttbar_reco
from tt_semileptonic.production.weights import weights
from tt_semileptonic.production.features import features
from tt_semileptonic.config.categories_helper import add_categories_production

ak = maybe_import("awkward")


@producer(
    uses={ttbar_reco, weights, features, category_ids},
    produces={ttbar_reco, weights, features, category_ids},
)
def default(self: Producer, events: ak.Array, **kwargs) -> ak.Array:
    # ttbar chi2 reconstruction (must run before category_ids, which needs TTbar.chi2 /
    # TTbar.cos_theta_star for the chi2/cos(theta*) categories registered below)
    events = self[ttbar_reco](events, **kwargs)

    events = self[weights](events, **kwargs)
    events = self[features](events, **kwargs)

    # recompute category_ids now that the chi2/cos(theta*) categories are registered
    events = self[category_ids](events, **kwargs)

    return events


@default.pre_init
def default_pre_init(self: Producer) -> None:
    # register the chi2/cos(theta*) categories (config/categories_helper.py) before any of
    # `default`'s dependencies are instantiated. This must be `pre_init`, not `.init` on
    # `ttbar_reco` (which is where a first attempt put it): `category_ids` is a *sibling*
    # dependency of `ttbar_reco` in `default`'s `uses` set, and `category_ids.init()` snapshots
    # `config_inst.get_leaf_categories()` into a fixed categorizer map at that point. Sibling
    # dependencies in a plain `uses={...}` set are instantiated (and thus `.init()`ed) in
    # whatever order the set iterates -- not guaranteed to put `ttbar_reco` first -- so relying
    # on `ttbar_reco.init()` to register the categories in time for `category_ids.init()` to see
    # them is a race. `pre_init` on `default` itself runs before `create_dependencies()` creates
    # *any* of `default`'s dependencies (columnflow's `ArrayFunction.deferred_init`), so this is
    # deterministic regardless of set-iteration order. `add_categories_production` is itself
    # idempotent (checks/sets `config.x.added_categories_production`).
    if getattr(self, "config_inst", None):
        add_categories_production(self.config_inst)
