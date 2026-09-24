# AGENTS.md — tt_semileptonic

HEP analysis (CMS, tt → semileptonic, top variables) built on the **columnflow**
framework (law + order). Learning project: built up **incrementally**, one task in
the columnflow graph at a time — each task must actually run before starting the next.
See [README.md](README.md) for the physics scope and the task-graph description.

This file is written from the real code. The previous version was auto-generated and
hallucinated large parts of the columnflow API — if something here disagrees with the
code, trust the code and fix this file.

Companion docs: [SELECTION.md](SELECTION.md) (every selection step in detail, through
`cf.ReduceEvents`), [CHANGES.md](CHANGES.md) (running change log), and
[ISSUES.md](ISSUES.md) (framework bugs we hit and worked around — the XRootD exit hang
and the `cf.PlotCutflow` regression).

---

## Setup

```bash
cd /data/dust/user/lsilberg/columnflow/tt_semileptonic_2
source setup.sh dev          # "dev" is the setup name (.setups/dev.sh); NOT plain `source setup.sh`
```

Re-running the setup needs a fresh shell (it refuses if already set up).

### Input files are read from the local dcache mount, not XRootD

`law.cfg` `[outputs] lfn_sources` lists `local_desy_dcache` (`base: /pnfs/desy.de/cms/tier2`)
first, so input NanoAOD is read via the POSIX filesystem. This is deliberate: the XRootD
client bundled in the columnar sandbox **deadlocks in its `atexit` handler** after a
`root://` read (`XrdCl::DefaultEnv::Finalize` → `Poller::Stop` blocked on a semaphore).
The task finishes its work and writes output, then the process never exits and the parent
`law` sits in `waitpid` forever. `mttbar` avoids this the same way. If a needed LFN is not
on the DESY Tier-2 disk, columnflow falls through to the XRootD redirectors and the hang
can return for that branch. The `[local_desy_dcache]` section also needs
`rucio_report_access: False` (cf's cms flavor requires the entry on every lfn source).

### Grid proxy — still needed for job submission / remote fallback

Tasks that read NanoAOD from the remote redirector are guarded by columnflow's
`ensure_proxy`. If the proxy is missing/expired they fail with
`voms-proxy-info failed` / sandbox exit code 40. Renew:

```bash
voms-proxy-init -voms cms -rfc -valid 192:00
voms-proxy-info --all      # check "timeleft" on both the proxy and the "VO cms extension"
```

`cf.GetDatasetLFNs` and already-cached `cf.CalibrateEvents` outputs do **not** need a
live proxy, which is why earlier steps can look fine while `SelectEvents` fails.

---

## Running tasks

Wrapper scripts live in [scripts/](scripts/) (`run_cf_getdatasetlfns.sh`,
`run_cf_calibrateevents.sh`, `run_cf_selectevents.sh`). Canonical test invocation:

```bash
law run cf.SelectEvents --dataset tt_sl_powheg --version test \
    --calibrators default --selector default
```

- **`law run` takes minutes** (streams ~800 MB files over xrootd). The user runs and
  monitors these themselves — do not block a session waiting on one; hand it back.
- Test dataset: `tt_sl_powheg`. Test version: `test`.
- Default config `run3_tt_semileptonic_2024_nano_v15_small` (`limit_dataset_files=2`).
- `--calibrator` (singular) up to `CalibrateEvents`; `--calibrators` (plural) from
  `SelectEvents` on.
- Task namespace is `cf` (e.g. `cf.SelectEvents`), set in `law.cfg`.

### Forcing a task to regenerate (`--remove-output`)

Law caches by parameter combination (dataset/version/calibrators/selector/.../branch) and
won't rerun a task whose output already exists, even a stale or broken one. `--remove-output`
is a `depth,mode,run` CSV triple (see `law/task/base.py`):

1. **depth** -- how far up the requirement chain to also remove: an int (`0` = only this
   task, not its upstream requirements) or a task-family name where recursion stops (e.g.
   `cf.CalibrateEvents` removes everything from the target task up through, and including,
   the first `cf.CalibrateEvents` it finds).
2. **mode** -- `i` (interactive per-target confirm, default), `a` (remove all, no prompts),
   or `d` (dry run -- shows what would be removed without deleting).
3. **run** -- whether to actually run the task after removing (default `False`, i.e. by
   itself `--remove-output` only deletes and exits; a separate plain `law run` is needed
   afterward to regenerate).

To force-regenerate just one task's own output in a single command (e.g. after changing a
producer, not the selection/reduction upstream of it):

```bash
law run cf.ProduceColumns --dataset tt_sl_powheg --version test \
    --calibrators default --selector default --reducer cf_default --producer default --branch 0 \
    --remove-output 0,a,True
```

`depth=0` keeps `cf.ReduceEvents`/`cf.SelectEvents`/`cf.CalibrateEvents` caches untouched.
Bump the depth (or name the upstream task family) when the change is further back in the
graph -- e.g. `--remove-output 2,a,False` was needed for a `cf.SelectEvents`-level config
change (see the "New categories don't retroactively apply..." gotcha below), which forced
`cf.CalibrateEvents` to regenerate too but left the actual rerun to a separate follow-up
`law run` (`run=False`).

---

## Layout

| Path | What |
|---|---|
| `tt_semileptonic/config/run3/analysis_tt_semileptonic.py` | `order.Analysis` object — the entry point named in `law.cfg` |
| `tt_semileptonic/config/run3/config_helper.py` | builds the `order.Config`: datasets, `x.lepton_selection` / `x.jet_selection` params, `x.keep_columns`, channels (`e`=1, `mu`=2), taggers |
| `tt_semileptonic/config/*_helper.py` | categories, variables, corrections, datasets, defaults/groups |
| `tt_semileptonic/{calibration,selection,production,categorization,reduction}/` | `@calibrator` / `@selector` / `@producer` / `@categorizer` / `@reducer` functions. `default.py` = current work, `example.py` = columnflow template, `*_old.py` = scratch |
| `tt_semileptonic/tasks/base.py` | `TT_SEMILEPTONICTask(BaseTask)` with `task_namespace="tt_semileptonic"` (custom tasks only; the `cf.*` tasks are columnflow's) |
| `modules/columnflow/` | the framework (submodule) — read here for real API |
| `modules/cmsdb/` | dataset/campaign/process definitions (submodule) |
| `../mttbar/` | the analysis this is derived from — a **working** reference for selectors, `channel_id`, categories, etc. (its API can be ahead of ours; verify before copying) |

Decorator imports are `from columnflow.selection import Selector, selector`,
`from columnflow.production import Producer, producer`, etc. — plain columnflow, no
custom decorator layer.

---

## Framework gotchas

- **Lepton selection** lives in `production/lepton.py::lepton_definition` (config-driven
  from `cfg.x.lepton_selection.{mu,e}`: pt regimes, IDs, isolation, barrel veto,
  extra-lepton veto) called from `selection/leptons.py::lepton_selection` (steps
  `lepton` + `dilepton_veto`, `VetoMuon`/`VetoElectron` object collections). It writes
  the transient `Muon/Electron.pass_lepton` + `pass_veto_lepton` masks and the kept
  `channel_id` (per-event int8: 1 = e, 2 = mu, 0 = neither) and `pt_regime` (0/1/2).
  `channel_id` is **not** a NanoAOD column — `lepton_producer`, `cat_1e`, `cat_1m`
  `uses={"channel_id"}` and raise `did not receive any columns matching: channel_id` if
  the lepton selection did not run first. Reference: `../mttbar/mtt/selection/lepton.py`
  (still to port: triggers, 2D lepton-jet isolation, MET).
- **De-option per-event scalars before broadcasting against a jagged array.** A
  `N * ?int` (e.g. `ak.firsts(...)`) compared against `N * var * int` (a jet column)
  makes the *whole list* nullable — `N * option[var * bool]` — which survives
  `ak.fill_none(x, False)` and eventually turns a selection step into `?bool`
  (`SelectionResult event mask must be of type N * bool`). Fix: `ak.fill_none` the
  scalar to a sentinel first (see `selected_lepton_jet_mask`).
- **Physics-object collections need the full `{pt,eta,phi,mass}` in `uses`.** Events
  are read with NanoAOD (`vector`) behavior, so `events.Jet.pt` / `events.Muon.pt`
  raises `array does not have azimuthal coordinates` if only a subset (e.g. `pt`,`eta`)
  was requested. Always `uses={"Jet.{pt,eta,phi,mass}", ...}` even when you only cut on
  pt/eta.
- **`category_ids` runs a categorizer for *every leaf category*** (see
  `columnflow/production/categories.py::category_ids_init`), not just the ones you ask
  for on the CLI. Adding a category whose `@categorizer` reads a column that isn't
  produced yet breaks `SelectEvents`. This is why top-tag categories (`0t`/`1t`) were
  disabled until `selection/cutflow_features.py` started producing
  `cutflow.n_toptag_delta_r_lepton`, which `cat_0t`/`cat_1t` need — now re-enabled in
  `config/categories_helper.py`.
- **New categories don't retroactively apply to an already-cached `cf.SelectEvents`
  output for the same `--version`.** `category_ids` runs inside `cf.SelectEvents`; law
  only reruns a task when its declared parameters change, not when the config's
  categorizer set changes. Hit this re-testing the `0t`/`1t` re-enable: `cf.PlotCutflow`
  showed the new combined categories as completely empty (while `incl` was populated)
  until `cf.SelectEvents`/`cf.CalibrateEvents` were force-regenerated
  (`--remove-output 2,a,False`) for that version. Same class of staleness as the
  `custom_increment_stats` note below.
- **`jet_veto_map`'s eta-clipping warning is expected, and its own log message is
  misleading.** A handful of very forward jets (`|eta|` just past 5.19, the edge of the
  correctionlib map's valid domain -- normal at the detector's HF acceptance boundary)
  get clipped before the veto-map lookup; a couple of these per large sample is routine,
  not a sign of a JEC/JER/jetId bug. The warning text itself (columnflow's
  `selection/cms/jets.py`) is buggy though: it logs the same pre-clip value for both
  "detected" and "set to" (the actual `ak.where(...)` clipping happens on the lines
  *after* the log call is formatted) — the clipping itself is still applied correctly,
  only the printed message is wrong. Upstream columnflow code, not ours to fix.
- A `@selector`/`@producer` declares `uses=` (input columns it will read) and
  `produces=` (columns it creates); columnflow checks these against the array and
  raises if a declared column is missing. Sub-selectors/producers passed in `uses`
  are called as `events = self[sub](events, **kwargs)`.
- `SelectionResult(steps=..., objects=..., aux=...)`: `steps` = per-event bool masks
  ANDed into `results.event`; `objects` = index arrays applied in `ReduceEvents`;
  `aux` = free-form extras. Results combine with `results += other`.

---

## Current status

| Task | State |
|---|---|
| `cf.GetDatasetLFNs` | ✅ works |
| `cf.CalibrateEvents` (`--calibrator default`) | ✅ now runs `mc_weight` → `deterministic_seeds` → `jet_lepton_cleaner` (lepton-4-vector subtraction from contaminated jets, any matched PF lepton via `Jet.{muon,electron}Idx1/2`, not just the selected one) → `jet_energy` (JEC + JER on MC, nominal-only for now -- `uncertainty_sources: []`) via `calibration/jets.py`, ported from `mtt/calibration/jets.py`. AK4 fully before AK8; AK8's own MET propagation disabled (AK4 already handles it). Confirmed working after fixing a `Jet.eta` non-finite bug in `jet_lepton_cleaner` (see CHANGES.md) |
| `cf.SelectEvents` (`--selector default`) | ✅ runs on the full `mc` group (29 datasets, all branches). Steps: `METFilters`, `JSON` (golden-JSON, data only), `lepton` (pt-regime IDs + iso), `dilepton_veto`, `jet` (≥2 AK4, channel-dep. pt, tight jetId), `bjet` (≥1 UParT-medium), `met` (channel-dep. PuppiMET), `lepton_jet_2d` (high-pt only), `all_had_veto` (<2 GloParT top-tagged AK8, tight jetId), `jet_veto_map` (data + MC, bad-detector-region veto), `QCDSpikes` (QCD MC only, `selection/qcd_spikes.py`). `selection/cutflow_features.py` writes `cutflow.*` columns for `cf.PlotCutflowVariables`, which also unblocked re-enabling the `0t`/`1t` categories (`config/categories_helper.py`) and the fuller `default_categories` list (`defaults_and_groups_helper.py`). Tight `Jet`/`FatJet` jetId via `columnflow.production.cms.jet.{jet_id,fatjet_id}` (stored NanoAOD bit is unreliable, see JME bug thread linked in `selection/jets.py`/`fatjets.py`). Sub-selectors in `selection/{leptons,jets,met,lepton_jet_2d,fatjets}.py`; lepton defs + `channel_id`/`pt_regime` + `selected_lepton_jet_mask` from `production/lepton.py`. Not yet: triggers. Confirmed running with the new `CalibrateEvents` JEC/JER chain (Jet/MET inputs now come from calibrated events); `QCDSpikes`, `cutflow_features`, and the re-enabled `0t`/`1t` categories were added *after* that confirmed run and haven't been exercised yet |
| `cf.SelectEvents` on **data** | not re-tested since `json_filter` was added (was previously ❌, undiagnosed) |
| `cf.ReduceEvents` | ✅ works on the full `mc` group with `--reducer cf_default` (`default_reducer` config key points at a nonexistent name, pass explicitly). One dataset (`qcd_ht1000to1200_madgraph`, higher jet multiplicity than `tt_sl_powheg`) hit an OOM (`sandbox exit code -9`) at `--workers 20`; fixed with a smaller, task-specific chunk size (`law.cfg`'s `cf.ReduceEvents__chunked_io_chunk_size: 30000`, see the comment there for why) rather than capping workers globally |
| `cf.PlotCutflow` | ✅ works on the full `mc` group (`--processes all`, renamed from `default` -- see `config/defaults_and_groups_helper.py::set_process_groups`) |
| `cf.ProduceColumns` | ✅ runs the weight-producer chain (`production/{weights,gen_top,btag,default}.py`): electron/muon SF, pileup weight, the real 2024 UParTAK4_kinfit b-tag SF (`upart_btag_weights`, `production/btag.py` -- not yet in `cfg.x.event_weights`, see CHANGES.md), `normalization_weights` (confirms all 29 MC datasets' `cmsdb` cross sections are populated at 13.6 TeV -- resolves `CORRECTIONS_QUESTIONS.md` #13), top-pt reweighting for ttbar. Also runs `production/features.py`: `ht`/`n_jet`/`n_fatjet`/`n_muon`/`n_electron`/`dijet_mass`/`dijet_delta_r`/`jet_lep_pt_rel`/`jet_lep_delta_r`. Also runs `production/ttbar_reco.py::ttbar_reco` (ported from `mtt/production/ttbar_reco.py`): combinatorial chi2 assignment of lepton/neutrino/jets to the leptonic and hadronic top legs (resolved regime) or lepton/neutrino/jets + top-tagged AK8 jet (boosted regime), reusing `production/neutrino.py::neutrino_candidates` and the `Lepton` column built during `cf.SelectEvents`; config side (`cfg.x.chi2_parameters`, `cfg.x.ttbar_reco_settings`, the `chi2`/`top_had_*`/`top_lep_*`/`cos_theta_star` variables) was already in place. Deliberately deferred from `ttbar_reco` to keep that step reviewable: gen-level matching (mtt's `ttbar_gen` producer reads `GenPart.hasFlags(...)`, which breaks the same way `production/gen_top.py` already found -- no coffea NanoAOD behavior on `GenPart` read back from `cf.ReduceEvents`' parquet during `cf.ProduceColumns`). Recomputing `category_ids` for the chi2/cos(theta*)-dependent categories is now wired up too (`cfg.x.categorization.chi2_max`, the `sel_chi2pass`/`sel_chi2fail`/`sel_acts_*` categorizers in `production/categories.py`, registered via `law.cfg`'s `categorization_modules`; `production/default.py` reruns `category_ids` after `ttbar_reco`) but **not yet run/confirmed** -- see CHANGES.md. Confirmed on `tt_sl_powheg` (single branch) with the current producer chain; not yet re-exercised on the full `mc` group since the b-tag SF / features / ttbar_reco additions (last full-`mc` confirmation predates them). Bugs found and fixed along the way: missing `Muon.{phi,mass}` in `uses`; `GenPart.hasFlags` unavailable post-`ReduceEvents`; `btag_weights_post_init`'s hardcoded Run-2-era `btag_uncs` clobbering a `.derive()` override; `@ArrayFunction.post_init` not returning the wrapped function, silently rebinding the module-level name to `None` -- see CHANGES.md for all four |
| `cf.PlotVariables1D` (chi2 variables) | ✅ `chi2`/`chi2_lt100`/`top_had_mass`/`top_lep_mass`/`cos_theta_star` (`TTbar.*` from `ttbar_reco` above) confirmed plottable on `tt_sl_powheg` (single branch) |
| `cf.CreateHistograms` | ⏭️ next -- combines the weight columns above into one per-event weight via `--hist-producer all_weights` (`cfg.x.default_hist_producer`). First test: `law run cf.CreateHistograms --dataset tt_sl_powheg --version test --calibrators default --selector default --reducer cf_default --producers default --hist-producer all_weights --variables electron_pt,muon_pt --branch 0` (note `--producers`, plural, unlike `cf.ProduceColumns`'s singular `--producer` -- `ProducersMixin`/`ProducerClassesMixin` in `columnflow/tasks/framework/mixins.py`). Things to check once it runs: does the histogram exist per category/process (`incl`, `1e`, `1m`, `1e__0t`, ... from the re-enabled categories) and shift (`nominal`); is `normalization_weight` scaling the yield sensibly (order-of-magnitude check against `cfg.x.luminosity` × cross section); `btag_weight` is real now but still has zero effect on yields since it's not in `cfg.x.event_weights` (see the `cf.ProduceColumns` row). Same worker/OOM caution as `cf.ReduceEvents` applies once scaling to the full `mc` group -- start with low `--workers` and watch memory before a full run |
| beyond | 🚧 Still not started: triggers, MET-φ correction (blocked on a 2024 JME file not yet published), `electron_scale_smear`/muon calibrators, gen-level ttbar matching (see the `cf.ProduceColumns` row above). The chi2/cos(theta*) category wiring is in but not yet run/confirmed -- also see that row |

Dataset groups (fixed for the 2024 names): `all` (43), `mc` (29), `bkg` (28),
`signal` (1 = `tt_sl_powheg`), `data` (14), plus `tt`/`st`/`w`/`dy`/`qcd`/`vv`. Run a
group with `law run cf.SelectEventsWrapper --datasets <group> --branch 0 …`.

### Known config inconsistencies (not yet cleaned up)

- `config/defaults_and_groups_helper.py`: `default_reducer` = `"default"`, but only
  `cf_default` (from `columnflow.reduction.default`) and `example` are registered in
  `law.cfg`'s `reduction_modules`. Same class of mismatch as the old `default_calibrator`
  one (now fixed -- `calibration/default.py`'s `default` is the real, actually-used
  calibrator). Pass `--reducer cf_default` explicitly.

### Cutflow / plotting

`config/defaults_and_groups_helper.py` has been trimmed to what currently exists (the
full m(ttbar)-style config is kept commented for later):

- `default_categories` / `category_groups["default"]` = `["incl", "1e", "1m"]`
- `selector_step_groups["default"]` = `["lepton", "jet"]` (must match the
  `SelectionResult` step names — `missing_selector_step_strategy = raise`)

Cutflow plot (needs all `SelectEvents` branches merged, so `--branch 0` does not apply;
`_small` config keeps it cheap):

```bash
law run cf.PlotCutflow --version test --calibrators default --selector default \
    --datasets mc --processes default --categories incl --selector-steps lepton,jet
```

Two things this depends on:
- `custom_increment_stats` writes `num_events_per_process` (columnflow's
  `normalization_weights`, run in `cf.MergeSelectionMasks` for MC, needs it).
- `cf.PlotCutflow` uses `tt_semileptonic.plotting.cutflow.plot_cutflow` (set in
  `law.cfg` `[luigi_cf.PlotCutflow]`), a wrapper working around columnflow PR #783
  which left the variable axis unreduced. See CHANGES.md.
