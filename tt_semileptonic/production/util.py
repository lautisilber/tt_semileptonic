# coding: utf-8

"""
Helper functions for the ttbar chi2 reconstruction (production/ttbar_reco.py). Ported from
mtt/production/util.py and mtt/util.py -- only the pieces that reconstruction actually needs;
columnflow's own ``columnflow.production.util`` already provides ``lv_xyzt``/``lv_mass``/
``lv_sum``/``attach_coffea_behavior``/``delta_r_match`` etc., so those are not duplicated here.
"""
import math
import itertools

from columnflow.util import maybe_import

ak = maybe_import("awkward")
np = maybe_import("numpy")


def ak_argcartesian(*arrs, as_type=np.uint8):
    """
    Like `ak.argcartesian`, but allows specifying a custom
    type for the index instead of the default `np.uint64`.
    """
    return tuple(
        ak.values_astype(item, as_type)
        for item in ak.unzip(ak.argcartesian(arrs))
    )


def ak_arg_grouped_combinations(
    array: ak.Array,
    group_sizes: list[int],
    axis: int = 1,
    cache: dict[int, tuple[ak.Array]] = None,
    as_type=np.uint8,
) -> tuple[tuple[ak.Array]]:
    """
    Like `ak.argcombinations`, but considers all possible ways to arrange
    the entries of an input `array` into non-overlapping groups with specified
    sizes `group_sizes`.

    Optionally, an `axis` along which to build the combinations can be specified
    (default is `1`).

    An optional `cache` dictionary with pre-computed index combinations can
    be given.

    Returns a nested tuple of unzipped index arrays (`combinations`) organized
    by group index and object position within the group. For example,
    `combinations[0][2]` yields the index of the third object in the first
    group.
    """
    if cache is None:
        cache = {}

    n_groups = len(group_sizes)
    if n_groups < 1:
        raise ValueError("at least one group size is required")

    # build combinations for each individual group size
    for n in group_sizes:
        if n not in cache:
            cache[n] = tuple(
                ak.values_astype(item, as_type)
                for item in ak.unzip(
                    ak.argcombinations(array, n, axis=axis),
                )
            )

    combs = [cache[n] for n in group_sizes]

    # build cartesian product of all different-size combinations
    comb_prod = tuple(
        ak.values_astype(item, as_type)
        for item in ak.unzip(
            ak.argcartesian([c[0] for c in combs]),
        )
    )

    # -- exclude combinations with a common index across any two groups

    keep = ak.ones_like(comb_prod[0], dtype=bool)
    # loop over all configurations of object indices within groups
    for obj_idxs in itertools.product(*(range(n) for n in group_sizes)):
        # loop over all combinations of two groups
        for g_idx_1, g_idx_2 in itertools.product(range(n_groups), range(n_groups)):
            # skip lower triangle
            if g_idx_1 >= g_idx_2:
                continue
            # drop cases where the same index is contained in two groups
            keep = keep & (
                combs[g_idx_1][obj_idxs[g_idx_1]][comb_prod[g_idx_1]] !=
                combs[g_idx_2][obj_idxs[g_idx_2]][comb_prod[g_idx_2]]
            )

    # apply filter to combination product
    comb_prod_filtered = tuple(p[keep] for p in comb_prod)

    # build index arrays from combinations product and return
    grouped_combs = tuple(
        tuple(
            ak.values_astype(
                c[comb_prod_filtered[g_idx]],
                as_type,
            )
            for c in combs[g_idx]
        )
        for g_idx in range(n_groups)
    )

    return grouped_combs


def iter_chunks(*arrays, max_chunk_size):
    """
    Iterate over one or more identically-sized `arrays` in chunks of at most `max_chunk_size`
    events. If `max_chunk_size` is negative or zero, no chunking is done.
    """
    size = len(arrays[0])
    if any(len(arr) != size for arr in arrays[1:]):
        lengths_str = ", ".join(str(len(arr)) for arr in arrays)
        raise ValueError(f"array length mismatch: {lengths_str}")

    n_chunks = 1
    if max_chunk_size > 0:
        n_chunks = int(math.ceil(size / max_chunk_size))

    if n_chunks == 1:
        yield arrays
        return

    for i_chunk in range(n_chunks):
        end = min(size, (i_chunk + 1) * max_chunk_size)
        slc = slice(i_chunk * max_chunk_size, end)
        yield tuple(a[slc] for a in arrays)
