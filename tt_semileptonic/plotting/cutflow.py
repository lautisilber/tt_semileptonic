# coding: utf-8

"""
Cutflow plotting.
"""

from __future__ import annotations

from columnflow.util import maybe_import
from columnflow.plotting.plot_functions_1d import plot_cutflow as cf_plot_cutflow

od = maybe_import("order")
hist = maybe_import("hist")


def plot_cutflow(
    hists: dict,
    config_inst: "od.Config",
    category_inst: "od.Category",
    **kwargs,
):
    """
    Thin wrapper around :py:func:`columnflow.plotting.plot_functions_1d.plot_cutflow`.

    columnflow PR #783 ("Improve leaf category handling in histograms") replaced
    ``h[{"category": sum, self.variable: sum}]`` in ``cf.PlotCutflow.run`` with
    ``select_category_bins(...)``, which reduces only the ``category`` axis. The variable
    axis (``event`` by default) is therefore left in place and the 1D ``plot_cutflow``
    receives a 2D ``(step, <variable>)`` histogram -> ``hist.plot_stack`` raises
    "Please project to 1D before calling plot".

    Here we restore the pre-#783 behaviour by summing every axis except ``step`` (an
    event-count cutflow never wants any other axis), then delegate to the upstream
    implementation. Drop this and the ``[cf.PlotCutflow] plot_function`` entry in
    ``law.cfg`` once columnflow reduces the variable axis itself.

    Task call::

        law run cf.PlotCutflow --version test --calibrators default --selector default \\
            --datasets mc --processes all --categories incl
    """
    reduced = {}
    for key, h in hists.items():
        extra_axes = [ax for ax in h.axes.name if ax != "step"]
        reduced[key] = h[{ax: sum for ax in extra_axes}] if extra_axes else h

    return cf_plot_cutflow(reduced, config_inst, category_inst, **kwargs)
