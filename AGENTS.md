# AGENTS.md — tt_semileptonic

HEP analysis (CMS, tt → semileptonic, top variables) built on the **columnflow**
framework (law + order). Learning project: built up **incrementally**, one task in
the columnflow graph at a time — each task must actually run before starting the next.
See [README.md](README.md) for the physics scope and the task-graph description.

This file is written from the real code. The previous version was auto-generated and
hallucinated large parts of the columnflow API — if something here disagrees with the
code, trust the code and fix this file.

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

- **`channel_id` is not a NanoAOD column.** It is produced by the selector
  (1 = e channel, 2 = mu channel, 0 = neither), then written with
  `set_ak_column(events, "channel_id", ...)`. `lepton_producer`, `cat_1e`, `cat_1m`
  all `uses={"channel_id"}` and will raise `did not receive any columns matching:
  channel_id` if no lepton-selection step ran first. Reference impl:
  `../mttbar/mtt/selection/lepton.py`.
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
| `cf.SelectEvents` (`--selector default`) | ✅ works — clean end-to-end run, both branches, ~42% selection efficiency (≥2 jets AND exactly one e or µ). `lepton_selection` produces `channel_id`; `category_ids` does channel categories only |
| `cf.ReduceEvents` | ⏭️ next |
| beyond | ⛔ not started |

### Known config inconsistencies (not yet cleaned up)

- `config/defaults_and_groups_helper.py`: `default_calibrator` = `"skip_jecunc"`, but
  only `default` exists in `calibration/default.py` (`skip_jecunc` is commented out).
  Scripts pass `--calibrator default` explicitly, so it works.
- Same file: `default_categories` lists `1m__0t`, `1e__1t`, … which won't exist while
  the `0t`/`1t` categories are commented out. Matters for later `--categories`
  defaults (plotting), not for `SelectEvents`.
- `law.cfg` `production_modules` references `tt_semileptonic.production.default`, which
  doesn't exist (the file is `production/lepton.py`). Harmless for now; fix when adding
  a producer.
