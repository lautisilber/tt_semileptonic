# coding: utf-8

"""
Helper factories for constructing categorizers. Ported from mtt/categorization/util.py --
only the pieces production/categories.py needs (``make_categorizer_not``, used for
``sel_chi2fail``, and ``make_categorizer_range``, used for the ``sel_acts_*`` bins).
"""
from typing import Optional

from columnflow.columnar_util import Route, TaskArrayFunction
from columnflow.util import maybe_import
from columnflow.categorization import Categorizer, categorizer

np = maybe_import("numpy")
ak = maybe_import("awkward")


def make_categorizer_not(name: str, input_categorizer: Categorizer):
    """
    Construct a categorizer that corresponds to the logical *NOT* of a given input categorizer.
    """
    @categorizer(cls_name=name, uses={input_categorizer})
    def cat(self: Categorizer, events: ak.Array, **kwargs) -> ak.Array:
        for dep in self.uses:
            if not isinstance(dep, TaskArrayFunction):
                continue
            events = self[dep](events, **kwargs)

        events, input_mask = self[input_categorizer](events, **kwargs)
        return events, ~input_mask

    return cat


def make_categorizer_range(
    name: str,
    route: str,
    min_val: float,
    max_val: float,
    route_func: Optional[callable] = None,
    **decorator_kwargs,
):
    """
    Construct a categorizer that evaluates to *True* whenever the value of the specified *route*
    lies between *min_val* and *max_val*. If supplied, a *route_func* is applied to the route
    value before performing the comparison.
    """
    route_func_name = getattr(route_func, "__name__", "<lambda>")
    route_repr = f"{route_func_name}({route})" if route_func else route

    @categorizer(cls_name=name, **decorator_kwargs)
    def cat(self: Categorizer, events: ak.Array, **kwargs) -> ak.Array:
        f"""Select only events where value of {route_repr} is in range ({min_val}, {max_val})."""
        for dep in self.uses:
            if not isinstance(dep, TaskArrayFunction):
                continue
            events = self[dep](events, **kwargs)

        val = Route(route).apply(events)
        if route_func:
            val = route_func(val)

        mask = (min_val <= val) & (val < max_val)
        return events, mask

    return cat
