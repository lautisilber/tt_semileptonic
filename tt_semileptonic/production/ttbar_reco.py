# coding: utf-8

"""
Column production for ttbar mass reconstruction via a chi2 minimization over lepton/jet/neutrino
assignments (the ``ttbar_reco`` producer). Ported from mtt/production/ttbar_reco.py (mttbar's
``ttbar`` producer), with these adaptations:
  - reads tt_semileptonic's ``Lepton`` column directly (already built by
    ``production/lepton.py::lepton_producer`` during ``cf.SelectEvents`` and kept through
    ``cf.ReduceEvents``) instead of recomputing it via mttbar's ``choose_lepton``
  - a single (eager) merge strategy across jet-multiplicity hypotheses, dropping mttbar's
    "lazy" alternative merge mode
  - no built-in profiling/verbosity machinery (mtt.profiling_tools.Profiler, a module we do
    not have); just one progress message per chunk

Confirmed running via ``cf.ProduceColumns`` and plottable via ``cf.PlotVariables1D`` on
``tt_sl_powheg`` (see CHANGES.md).

Not ported (deliberately, to keep this step reviewable on its own -- see CHANGES.md):
  - gen-level truth matching (mttbar's ``ttbar_gen`` producer and the ``TTbar.gen_*`` /
    ``GenTTbar.*`` columns it feeds; ``config/variables_helper.py`` already has variable
    definitions for them, ready for when that follow-up lands)

The chi2/cos(theta*) categories (``config/categories_helper.py::add_categories_production``,
the ``sel_chi2pass``/``sel_acts_*`` categorizers in ``production/categories.py``) are
registered from ``production/default.py``'s ``@default.pre_init`` hook, not from an ``.init``
hook here -- see that file's comment for why (``category_ids``, a *sibling* dependency of
``ttbar_reco`` in ``default``'s ``uses``, snapshots the config's leaf-category list at its own
``.init`` time, and the instantiation order between sibling dependencies within a plain
``uses={...}`` set is not guaranteed). Added in the same change as this file but not yet
run/confirmed the way the reconstruction itself has been.
"""
import itertools
import math

import law

from columnflow.production import Producer, producer
from columnflow.production.util import lv_xyzt, lv_mass, lv_sum
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column, EMPTY_FLOAT

from tt_semileptonic.production.util import ak_argcartesian, ak_arg_grouped_combinations, iter_chunks
from tt_semileptonic.production.neutrino import neutrino_candidates

ak = maybe_import("awkward")
np = maybe_import("numpy")
coffea = maybe_import("coffea")
maybe_import("coffea.nanoevents.methods.nanoaod")

logger = law.logger.get_logger(__name__)


@producer(
    uses={
        neutrino_candidates,
        "Lepton.{pt,eta,phi,mass}",
        "Jet.{pt,eta,phi,mass}",
        "FatJetTopTagDeltaRLepton.{pt,eta,phi,mass,msoftdrop}",
    },
    produces={
        neutrino_candidates,
        "TTbar.*",
    },
)
def ttbar_reco(
    self: Producer,
    events: ak.Array,
    task: law.Task,
    **kwargs,
) -> ak.Array:
    """
    Reconstruct the ttbar pair in the semileptonic decay mode. This is done by evaluating all
    possibilities of assigning the lepton, jets, and neutrino to the hadronic and leptonic legs
    of the decay, in terms of a chi2 metric. The configuration with the lowest chi2 out of all
    possibilities is selected.

    Settings are read from ``cfg.x.ttbar_reco_settings``:
      - *n_jet_max*: limit the number of jets per event to at most this number
      - *n_jet_lep_range*: min/max number of jets assignable to the leptonic top decay
      - *n_jet_had_range*: min/max number of jets assignable to the hadronic top decay
      - *n_jet_ttbar_range*: min/max number of jets assignable to the ttbar decay overall
        (inferred from *n_jet_lep_range*/*n_jet_had_range* if not given)
      - *max_chunk_size*: process events in sub-chunks of at most this size to bound peak memory
    """
    settings = self.config_inst.x.ttbar_reco_settings
    n_jet_max = settings["n_jet_max"]
    n_jet_lep_range = settings["n_jet_lep_range"]
    n_jet_had_range = settings["n_jet_had_range"]
    n_jet_ttbar_range = settings.get("n_jet_ttbar_range")
    max_chunk_size = settings["max_chunk_size"]
    if callable(max_chunk_size):
        max_chunk_size = max_chunk_size(self.dataset_inst)

    if n_jet_ttbar_range is None:
        n_jet_ttbar_range = (
            n_jet_lep_range[0] + n_jet_had_range[0],
            n_jet_lep_range[1] + n_jet_had_range[1],
        )

    for range_par in (n_jet_lep_range, n_jet_had_range, n_jet_ttbar_range):
        assert len(range_par) == 2
        assert range_par[0] >= 1
        assert range_par[1] <= n_jet_max

    # load coffea behaviors for simplified arithmetic with vectors (events read from
    # cf.ReduceEvents' parquet output don't carry them anymore)
    events = ak.Array(events, behavior=coffea.nanoevents.methods.nanoaod.behavior)
    events["Jet"] = ak.with_name(events.Jet, "PtEtaPhiMLorentzVector")
    events["FatJetTopTagDeltaRLepton"] = ak.with_name(events.FatJetTopTagDeltaRLepton, "PtEtaPhiMLorentzVector")

    # reconstruct neutrino candidates
    events = self[neutrino_candidates](events, **kwargs)
    nu_cands = events["NeutrinoCandidates"]

    lepton = ak.with_name(events.Lepton, "PtEtaPhiMLorentzVector")

    # -- AK8 jets: only top-tagged jets well separated from the main lepton (selection/fatjets.py)
    topjet = events.FatJetTopTagDeltaRLepton

    # tag events as boosted if there is at least one such AK8 jet
    is_boosted = ak.fill_none(ak.num(topjet, axis=1) >= 1, False)

    # -- AK4 jets: only keep the first `n_jet_max` jets per event
    jet = events.Jet[ak.local_index(events.Jet) < n_jet_max]

    # well separated from AK8 jets (deltaR >= 1.2)
    delta_r_jet_topjet = ak.min(jet.metric_table(topjet), axis=2)
    jet_isolated = ak.fill_none(delta_r_jet_topjet > 1.2, True)
    jet = jet[jet_isolated]

    # split jet array into boosted/resolved cases
    jet_resolved = ak.where(is_boosted, [[]], jet)
    jet_boosted = ak.where(~is_boosted, [[]], jet)

    # pack arrays to ensure contiguous memory and trim unreachable entries
    jet_resolved = ak.to_packed(jet_resolved)
    jet_boosted = ak.to_packed(jet_boosted)

    # make lorentz vectors
    topjet_lv = lv_xyzt(topjet)
    jet_lv = {
        "resolved": lv_xyzt(jet_resolved),
        "boosted": lv_xyzt(jet_boosted),
    }
    lepton_lv = lv_xyzt(ak.unflatten(lepton, counts=1))
    nu_cands_lv = lv_xyzt(nu_cands)

    # -- handle combinatorics

    # keep the best-chi2 combination found so far, updating after each round of combinatorics
    def merge_sequential(best_results, new_results):
        if best_results is None:
            return new_results
        new_chi2, best_chi2 = new_results["chi2"], best_results["chi2"]
        update = new_chi2 < best_chi2
        # handle missing values
        update = ak.fill_none(
            ak.where(ak.is_none(update), ~ak.is_none(new_chi2), update),
            False,
        )
        return {
            res_var: ak.to_packed(ak.where(
                update,
                new_results[res_var],
                best_results[res_var],
            ))
            for res_var in best_results
        }

    # builds all possible ways of arranging combinations into groups with fixed sizes (`n_jets`)
    def ttbar_combinatorics(jet_lv, topjet_lv, topjet_msoftdrop, lepton_lv, nu_cands_lv, n_jets, regime="resolved"):
        """
        Reconstruct the leptonically and hadronically decaying top quarks from combinations of
        final-state objects (AK4 jets, top-tagged AK8 jets [boosted only], lepton, neutrino
        candidates), for a fixed jet multiplicity `n_jets`.

        In the `resolved` regime, the decays of both top quarks are reconstructed from AK4 jets;
        `n_jets` is `(n_jet_lep, n_jet_had)`. In the `boosted` regime, the hadronically decaying
        top quark is identified with the (highest-pt) top-tagged AK8 jet, and only the leptonic
        decay is reconstructed from AK4 jets; `n_jets` is `(n_jet_lep,)`.
        """
        if regime == "resolved":
            assert len(n_jets) == 2
            is_boosted_regime = False
            n_jet_lep, n_jet_had = n_jets
        elif regime == "boosted":
            assert len(n_jets) == 1
            is_boosted_regime = True
            n_jet_lep = n_jets[0]
        else:
            assert False, f"unknown regime: {regime}"

        # jet index combinations for all possible groupings of jets into two distinct sets
        # with sizes `n_jet_lep` and `n_jet_had`
        jet_idx_combs = ak_arg_grouped_combinations(jet_lv, group_sizes=n_jets, axis=1)
        if is_boosted_regime:
            jet_idx_comb_lep = jet_idx_combs[0]
        else:
            jet_idx_comb_lep, jet_idx_comb_had = jet_idx_combs

        # index configurations for all choices of lepton, neutrino candidate,
        # and jet combination mapped to leptonic decay
        lnu_jetcomb_idx_prod = ak_argcartesian(
            lepton_lv,
            nu_cands_lv,
            jet_idx_comb_lep[0],
        )

        # retrieve chi2 parameters from config
        chi2_pars = self.config_inst.x.chi2_parameters[regime]

        # -- set up hypotheses for leptonically decaying tops

        jet_sum_lep = lv_sum((jet_lv[jet_idx] for jet_idx in jet_idx_comb_lep))
        hyp_top_lep = (
            lepton_lv[lnu_jetcomb_idx_prod[0]] +
            nu_cands_lv[lnu_jetcomb_idx_prod[1]] +
            jet_sum_lep[lnu_jetcomb_idx_prod[2]]
        )
        hyp_top_lep_chi2 = ((hyp_top_lep.mass - chi2_pars.m_lep) / chi2_pars.s_lep) ** 2
        hyp_n_jet_lep = ak.ones_like(hyp_top_lep_chi2, dtype=np.uint8) * n_jet_lep

        # -- set up hypotheses for hadronically decaying tops

        if regime == "resolved":
            jet_sum_had = lv_sum((jet_lv[jet_idx] for jet_idx in jet_idx_comb_had))
            hyp_top_had = jet_sum_had[lnu_jetcomb_idx_prod[2]]
            hyp_top_had_chi2 = ((hyp_top_had.mass - chi2_pars.m_had) / chi2_pars.s_had) ** 2
            hyp_n_jet_had = ak.ones_like(hyp_top_had_chi2, dtype=np.uint8) * n_jet_had

        # reduce hypotheses based on minimal total chi2 score
        if is_boosted_regime:
            hyp_top_chi2 = hyp_top_lep_chi2
        else:
            hyp_top_chi2 = hyp_top_lep_chi2 + hyp_top_had_chi2

        hyp_top_chi2_argmin = ak.argmin(hyp_top_chi2, axis=1, keepdims=True)

        # store final leptonic top
        top_lep = ak.firsts(hyp_top_lep[hyp_top_chi2_argmin])
        n_jet_lep = ak.firsts(hyp_n_jet_lep[hyp_top_chi2_argmin])
        top_lep_chi2 = ak.firsts(hyp_top_lep_chi2[hyp_top_chi2_argmin])

        # get mapped jet indices
        jetcomb_idx = lnu_jetcomb_idx_prod[2][hyp_top_chi2_argmin]
        jet_idxs_lep = ak.concatenate([
            jet_idx[jetcomb_idx]
            for jet_idx in jet_idx_comb_lep
        ], axis=1)

        # store final hadronic top
        if is_boosted_regime:
            top_had = ak.firsts(topjet_lv)
            top_had_chi2 = ((ak.firsts(topjet_msoftdrop) - chi2_pars.m_had) / chi2_pars.s_had) ** 2
            n_jet_had = ak.zeros_like(n_jet_lep, dtype=np.uint8)
            # array of empty lists
            jet_idxs_had = ak.values_astype(
                ak.drop_none(
                    ak.mask(
                        hyp_top_chi2_argmin,
                        ak.zeros_like(hyp_top_chi2_argmin, dtype=bool),
                        valid_when=True,
                    ),
                ),
                np.uint8,
            )
        else:
            top_had = ak.firsts(hyp_top_had[hyp_top_chi2_argmin])
            top_had_chi2 = ak.firsts(hyp_top_had_chi2[hyp_top_chi2_argmin])
            n_jet_had = ak.firsts(hyp_n_jet_had[hyp_top_chi2_argmin])
            jet_idxs_had = ak.concatenate([
                jet_idx[jetcomb_idx]
                for jet_idx in jet_idx_comb_had
            ], axis=1)

        chi2 = top_had_chi2 + top_lep_chi2

        return {
            "top_had": top_had,
            "top_lep": top_lep,
            "n_jet_had": n_jet_had,
            "n_jet_lep": n_jet_lep,
            "jet_idxs_had": jet_idxs_had,
            "jet_idxs_lep": jet_idxs_lep,
            "top_had_chi2": top_had_chi2,
            "top_lep_chi2": top_lep_chi2,
            "chi2": chi2,
        }

    # loop over all allowed multiplicities of jets assigned to the leptonic/hadronic top decays,
    # merging the best-chi2 result after each one
    def main_loop(jet_lv, topjet_lv, topjet_msoftdrop, lepton_lv, nu_cands_lv, regime):
        iter_n_jets = [range(n_jet_lep_range[0], n_jet_lep_range[1] + 1)]
        if regime == "resolved":
            iter_n_jets.append(range(n_jet_had_range[0], n_jet_had_range[1] + 1))

        comb_results = None
        for n_jets in itertools.product(*iter_n_jets):
            n_jet_ttbar = sum(n_jets)
            if (
                regime == "resolved" and
                not (n_jet_ttbar_range[0] <= n_jet_ttbar <= n_jet_ttbar_range[1])
            ):
                continue

            results = ttbar_combinatorics(
                jet_lv, topjet_lv, topjet_msoftdrop, lepton_lv, nu_cands_lv,
                n_jets=n_jets, regime=regime,
            )
            comb_results = merge_sequential(comb_results, results)

        return comb_results

    def apply_chunked(func, arrays, max_chunk_size, **kwargs):
        """
        Apply `func` to identically-sized `arrays` in a chunked way and merge the results
        (a dict of `ak.Array` objects), to bound peak memory during the combinatorics.
        """
        result = None
        size = len(arrays[0])
        n_chunks = max(1, int(math.ceil(size / max_chunk_size)))
        task.publish_message(f"ttbar reco ({kwargs.get('regime')}): {size} events in {n_chunks} sub-chunks")
        for arrays_chk in iter_chunks(*arrays, max_chunk_size=max_chunk_size):
            new_result = func(*arrays_chk, **kwargs)
            if result is None:
                result = new_result
            else:
                result = {
                    key: ak.to_packed(ak.concatenate([result[key], new_result[key]], axis=0))
                    for key in result
                }
        return result

    # apply main loop in both regimes
    comb_results = {}
    for regime in ("resolved", "boosted"):
        comb_results[regime] = apply_chunked(
            main_loop,
            (jet_lv[regime], topjet_lv, topjet.msoftdrop, lepton_lv, nu_cands_lv),
            regime=regime,
            max_chunk_size=max_chunk_size,
        )

    # merge regimes
    result_keys = set(comb_results["resolved"])
    assert result_keys == set(comb_results["boosted"]), "resolved and boosted result keys mismatched"
    comb_results = {
        key: ak.to_packed(ak.where(
            is_boosted,
            comb_results["boosted"][key],
            comb_results["resolved"][key],
        ))
        for key in result_keys
    }

    # store final top
    top_had = lv_mass(comb_results["top_had"])
    top_lep = lv_mass(comb_results["top_lep"])

    # store mapped jet indices and counts
    jet_idxs_had = comb_results["jet_idxs_had"]
    jet_idxs_lep = comb_results["jet_idxs_lep"]
    n_jet_had = comb_results["n_jet_had"]
    n_jet_lep = comb_results["n_jet_lep"]

    # store final chi2 scores
    top_had_chi2 = comb_results["top_had_chi2"]
    top_lep_chi2 = comb_results["top_lep_chi2"]
    chi2 = comb_results["chi2"]

    # sum over top quarks to form ttbar system
    ttbar_lv = lv_mass(top_had + top_lep)

    # -- calculate cos(theta*)

    # boost lepton + leptonic top quark to ttbar rest frame
    top_lep_ttrest = top_lep.boost(-ttbar_lv.boostvec)

    # get cosine from three-vector dot product and magnitudes
    cos_theta_star = ttbar_lv.pvec.dot(top_lep_ttrest.pvec) / (ttbar_lv.pvec.p * top_lep_ttrest.pvec.p)
    abs_cos_theta_star = abs(cos_theta_star)

    # -- calculate energy of hadronic and leptonic top
    top_had_energy = np.sqrt((top_had.mass) ** 2 + (top_had.pt) ** 2)
    top_lep_energy = np.sqrt((top_lep.mass) ** 2 + (top_lep.pt) ** 2)

    # write out columns
    for var in ("pt", "eta", "phi", "mass"):
        events = set_ak_column(events, f"TTbar.top_had_{var}", ak.fill_none(getattr(top_had, var), EMPTY_FLOAT))
        events = set_ak_column(events, f"TTbar.top_lep_{var}", ak.fill_none(getattr(top_lep, var), EMPTY_FLOAT))
        events = set_ak_column(events, f"TTbar.{var}", ak.fill_none(getattr(ttbar_lv, var), EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.top_had_energy", ak.fill_none(top_had_energy, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.top_lep_energy", ak.fill_none(top_lep_energy, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.n_jet_had", ak.fill_none(n_jet_had, -1))
    events = set_ak_column(events, "TTbar.n_jet_lep", ak.fill_none(n_jet_lep, -1))
    events = set_ak_column(events, "TTbar.n_jet_sum", ak.fill_none(n_jet_lep + n_jet_had, -1))
    events = set_ak_column(events, "TTbar.jet_idxs_had", ak.drop_none(jet_idxs_had))
    events = set_ak_column(events, "TTbar.jet_idxs_lep", ak.drop_none(jet_idxs_lep))
    events = set_ak_column(events, "TTbar.chi2_had", ak.fill_none(top_had_chi2, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.chi2_lep", ak.fill_none(top_lep_chi2, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.chi2", ak.fill_none(chi2, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.cos_theta_star", ak.fill_none(cos_theta_star, EMPTY_FLOAT))
    events = set_ak_column(events, "TTbar.abs_cos_theta_star", ak.fill_none(abs_cos_theta_star, EMPTY_FLOAT))

    return events
