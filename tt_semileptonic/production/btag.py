# coding: utf-8

"""
b-tag scale factor weight, for the 2024 UParT working point.

``columnflow.production.cms.btag.btag_weights`` (the stock producer) can't be used via
mttbar's ``.derive(cls_dict={"btag_uncs": ...})`` pattern as-is on our columnflow commit:
``btag_weights_post_init`` (``columnflow/production/cms/btag.py``) unconditionally
overwrites ``self.btag_uncs`` with a hardcoded Run-2-era name set (``hf``/``lf``/
``hfstats1``/``hfstats2``/``lfstats1``/``lfstats2``/``cferr1``/``cferr2``) *after*
``.derive()``'s ``cls_dict`` override has already been applied, silently clobbering it. (On
mttbar's older columnflow commit that reassignment is commented out, which is why their
identical ``.derive()`` pattern works there -- an upstream columnflow behavior change, not
a bug in mttbar's code.) The actual 2024 ``UParTAK4_kinfit`` correction set (in the
already-fetched ``btagging_preliminary.json.gz``, ``cfg.x.btag_sf`` in
``config/corrections_helper.py::btag_sf_cfg``) uses a different systematic-name set
(``fsrdef``/``hdamp``/``isrdef``/``jer``/``jes``/``mass``/``statistic``/``tune``), so
letting the hardcoded names win raises a correctionlib lookup error the moment ``up_hf`` is
requested, which the file doesn't have.

Fixed below by giving ``upart_btag_weights`` its own ``post_init``: it runs the stock
``btag_weights_post_init`` first (for the column-name bookkeeping unrelated to
``btag_uncs``: ``btag_config``, JEC-source detection, ``produces`` shift handling), then
restores the correct ``btag_uncs`` and swaps the wrongly-named varied-weight columns it
just added to ``produces`` for the correct ones.

Like mttbar's own config, ``btag_weight`` is *not* added to ``cfg.x.event_weights`` here --
folding a per-jet shape SF straight into the combined event weight changes the total
selected yield (it isn't renormalized), which is why mttbar's config only ever defines the
*intended* target column names for a "normalized" (per-jet-multiplicity-rescaled) version
(``normalized_btag_weight``/``normalized_btag_weight_upart`` in the shift-alias block of
``config_helper.py``) without ever implementing the producer that would write them. Until
that normalization step exists here too, ``upart_btag_weights`` only produces the
``btag_weight*`` columns for inspection/plotting; it has zero effect on histogram yields.
"""

from columnflow.production.cms.btag import btag_weights

#: 2024 UParTAK4_kinfit systematic names (config/corrections_helper.py::btag_sf_cfg),
#: distinct from btag_weights_post_init's hardcoded Run-2-era default
upart_btag_uncs = {
    "fsrdef": "fsrdef",
    "hdamp": "hdamp",
    "isrdef": "isrdef",
    "jer": "jer",
    "jes": "jes",
    "mass": "mass",
    "statistic": "statistic",
    "tune": "tune",
}

upart_btag_weights = btag_weights.derive(
    "upart_btag_weights",
    cls_dict={"btag_uncs": upart_btag_uncs},
)


@upart_btag_weights.post_init
def upart_btag_weights_post_init(self, task, **kwargs) -> None:
    # capture the correct uncs before the stock post_init clobbers self.btag_uncs
    correct_uncs = dict(self.btag_uncs)

    # `@btag_weights.post_init` doesn't return the wrapped function (columnflow's own
    # `ArrayFunction.post_init` docstring: "The decorator does not return the wrapped
    # function") -- it only sets `btag_weights.post_init_func`, and rebinds the
    # module-level name `btag_weights_post_init` to `None`. So the stock implementation
    # has to be reached via the class attribute, not an import.
    btag_weights.post_init_func(self, task, **kwargs)

    wrong_uncs = self.btag_uncs
    self.btag_uncs = correct_uncs

    # the stock post_init already added `produces` entries for the varied weight columns
    # using the wrong (Run-2-era) names -- swap them for the correct ones
    if task.global_shift_inst.is_nominal:
        for col_name in wrong_uncs.values():
            self.produces.discard(f"{self.weight_name}_{col_name}_{{up,down}}")
        for col_name in correct_uncs.values():
            self.produces.add(f"{self.weight_name}_{col_name}_{{up,down}}")
