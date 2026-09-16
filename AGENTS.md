# AGENTS.md — tt_semileptonic

HEP analysis (CMS, tt → semileptonic, top variables) built on the **columnflow**
framework (law + order). Learning project: built up **incrementally**, one task in
the columnflow graph at a time — each task must actually run before starting the next.
See [README.md](README.md) for the physics scope and the task-graph description.

This file is written from the real code. The previous version was auto-generated and
hallucinated large parts of the columnflow API — if something here disagrees with the
code, trust the code and fix this file.

Companion docs: [SELECTION.md](SELECTION.md) (every selection step in detail + the
difficulties overcome), [CHANGES.md](CHANGES.md) (running change log), and
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
  produced yet breaks `SelectEvents`. This is why top-tag categories (`0t`/`1t`) are
  currently commented out in `config/categories_helper.py` — `cat_0t`/`cat_1t` need
  `cutflow.n_toptag_delta_r_lepton`.
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
| `cf.CalibrateEvents` (`--calibrator default`) | ✅ works |
| `cf.SelectEvents` (`--selector default`) | ⚠️ jet/fatjet tight ID just added (`columnflow.production.cms.jet.{jet_id,fatjet_id}`, recomputed from the `jet_id` correctionlib file since the stored NanoAOD `jetId` bitmap is unreliable, see JME bug thread linked in `selection/jets.py`/`fatjets.py`), not yet re-run to confirm. Previously ✅ ran on MC with steps: `METFilters`, `lepton` (pt-regime IDs + iso), `dilepton_veto`, `jet` (≥2 AK4, channel-dep. pt, now + tight ID), `bjet` (≥1 UParT-medium), `met` (channel-dep. PuppiMET), `lepton_jet_2d` (high-pt only), `all_had_veto` (<2 GloParT top-tagged AK8, now + tight ID). Sub-selectors in `selection/{leptons,jets,met,lepton_jet_2d,fatjets}.py`; lepton defs + `channel_id`/`pt_regime` + `selected_lepton_jet_mask` from `production/lepton.py`. Jets lepton-cleaned via `Jet.{muon,electron}Idx1/2`. Not yet: triggers. Re-check efficiency after each addition |
| `cf.SelectEvents` on **data** | ❌ fails (14 `data_*` datasets), not yet diagnosed. Selector applies no golden-JSON / MET-filter cuts on data. `columnflow.production.cms.seeds` "optional route not found" warnings on data are harmless (MC-only seed inputs). |
| `cf.ReduceEvents` | ⏭️ next |
| beyond | ⛔ not started |

Dataset groups (fixed for the 2024 names): `all` (43), `mc` (29), `bkg` (28),
`signal` (1 = `tt_sl_powheg`), `data` (14), plus `tt`/`st`/`w`/`dy`/`qcd`/`vv`. Run a
group with `law run cf.SelectEventsWrapper --datasets <group> --branch 0 …`.

### Known config inconsistencies (not yet cleaned up)

- `config/defaults_and_groups_helper.py`: `default_calibrator` = `"skip_jecunc"`, but
  only `default` exists in `calibration/default.py` (`skip_jecunc` is commented out).
  Scripts pass `--calibrator default` explicitly, so it works.
- `law.cfg` `production_modules` references `tt_semileptonic.production.default`, which
  doesn't exist (the file is `production/lepton.py`). Harmless for now; fix when adding
  a producer.

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
