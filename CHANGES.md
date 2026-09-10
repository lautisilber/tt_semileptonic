# Changes

Running log of notable changes, newest first. Each entry corresponds to roughly one
commit's worth of work.

---

## Fix dataset and process groups for the 2024 dataset names

`defaults_and_groups_helper.py`: the `data`, `bkg` and `signal` dataset groups (and the
`bkg` process group) were ported from mttbar and referenced names that do not exist in
the 2024 cmsdb campaign, so they resolved to the wrong set or to nothing.

- `config.x.dataset_groups`:
  - `data`: `data_egamma_*` → `data_e_*` (was matching only the 7 muon datasets)
  - `bkg`: `tt_dl`/`tt_hl` → `tt_dl_powheg`/`tt_fh_powheg`, and add the diboson
    patterns `ww_*`/`wz_*`/`zz_*` which were missing entirely (23 → 28 datasets)
  - `signal`: `tt_sl` → `tt_sl_powheg` (was resolving to 0 datasets)
  - new `mc` group: all simulation, i.e. `all` (43) minus `data` (14) = 29 datasets
    (= `signal` + `bkg`). Spelled out as patterns because groups can only add.
- `config.x.process_groups`:
  - `bkg`: `tt_hl` → `tt_fh` (no `tt_hl` process exists)
  - add a `data` group (`["data"]`)

The other dataset groups (`tt`, `st`, `w`, `w_lnu`, `dy`, `qcd`, `vv`, `all`) were
already correct.

Usage: run `cf.SelectEvents` over all backgrounds with

```bash
law run cf.SelectEventsWrapper --datasets bkg --branch 0 \
    --version test --calibrators default --selector default --workers 4
```

### Status by dataset group (cf.SelectEvents, `--branch 0`, small config)

| group | result |
|---|---|
| `signal` (`tt_sl_powheg`) | ✅ works |
| `bkg` (28 MC) | ✅ all run |
| `data` (14) | ❌ **does not work yet** — not yet diagnosed. The selector also
  applies no golden-JSON / MET-filter selection on data. The
  `columnflow.production.cms.seeds` warnings seen during the data run
  (`optional route 'Pileup.nPU' / 'GenJet.pt' / 'GenPart.pt' not found`) are
  **harmless** — `deterministic_seeds` just drops those MC-only inputs and seeds
  from run/lumi/event; not the cause of the failure. |

---

## cf.SelectEvents working: lepton selection, channel_id, XRootD hang fix

Got `cf.SelectEvents` to run end-to-end (both branches of the `small` config,
~42% selection efficiency, clean process exit).

### Selection

- **New file `tt_semileptonic/production/lepton.py`**: `lepton_producer` merges the
  `Muon` and `Electron` collections into a single `Lepton` collection per event,
  chosen by `channel_id`.
- **`tt_semileptonic/selection/default.py`**: new `lepton_selection` sub-selector that
  computes `channel_id` (1 = e channel, 2 = mu channel, 0 = neither) and writes it as
  a column via `set_ak_column`, then wire `lepton_selection` + `lepton_producer` +
  `category_ids` into the exposed `default` selector.
  - Why: `channel_id` is **not** a NanoAOD field and nothing was producing it, so
    `lepton_producer` / `cat_1e` / `cat_1m` failed with
    `did not receive any columns matching: channel_id`.

### Categorization

- **`tt_semileptonic/categorization/default.py`**: replace `cat_2j` with the channel
  categorizers `cat_1e` / `cat_1m` (plus `cat_0t` / `cat_1t` stubs for later), fix the
  `cat_incl` dtype.
- **`tt_semileptonic/config/categories_helper.py`**: rename selection keys
  `sel_*` → `cat_*`; disable the `0t` / `1t` categories and the `n_top_tags` group
  until top-tagging exists.
  - Why: `category_ids` runs a categorizer for **every leaf category** in the config
    (see `columnflow/production/categories.py::category_ids_init`), not just the ones
    requested on the CLI. `cat_0t` / `cat_1t` read `cutflow.n_toptag_delta_r_lepton`,
    which is not produced yet, so leaving them enabled breaks `SelectEvents`.

### Infrastructure (`law.cfg`)

- Register `tt_semileptonic.categorization.default` in `categorization_modules`.
- **Read input NanoAOD from the DESY Tier-2 dcache POSIX mount**: add a
  `[local_desy_dcache]` section (`base: /pnfs/desy.de/cms/tier2`,
  `rucio_report_access: False`) as the **first** `[outputs] lfn_sources` entry.
  - Why: the XRootD client bundled in the columnar sandbox **deadlocks in its `atexit`
    handler** after a `root://` read (`XrdCl::DefaultEnv::Finalize` → `Poller::Stop`
    blocked on a semaphore). The task finishes its work and writes output, then the
    process never exits and the parent `law` sits in `waitpid` forever. `mttbar`
    avoids this the same way. `rucio_report_access` is required by cf's cms flavor on
    every lfn source.

### Docs

- **Rewrite `AGENTS.md`** from the actual code — the previous version was
  auto-generated and contained a hallucinated columnflow API. New content: setup and
  run instructions, the `channel_id` / `category_ids` / XRootD gotchas, and a
  task-graph status table.
- `scripts/run_cf_selectevents.sh`: note the `mttbar`-equivalent command.

### Known loose ends

- `law.cfg` `production_modules` references `tt_semileptonic.production.default`, which
  does not exist (the file is `production/lepton.py`). Harmless for now; point it at
  `tt_semileptonic.production.lepton` when a producer is added.
- `config/defaults_and_groups_helper.py`: `default_calibrator = "skip_jecunc"` but
  only `default` exists in `calibration/default.py`; `default_categories` lists
  `1m__0t`, `1e__1t`, … which no longer exist while `0t`/`1t` are disabled. Neither
  affects `SelectEvents` (scripts pass `--calibrator default` explicitly).
