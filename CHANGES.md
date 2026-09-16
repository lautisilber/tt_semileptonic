# Changes

Running log of notable changes, newest first. Each entry corresponds to roughly one
commit's worth of work.

---

## Weight-producer chain (pu/muon/electron/normalization/top_pt) + b-tag SF placeholder

Ported the weight side of `mtt/production/weights.py` -- the config already had
`cfg.x.event_weights` listing `pu_weight` / `muon_weight` / `electron_weight` /
`normalization_weight`, plus the SF config objects, but nothing actually computed and
persisted those columns.

- **New `tt_semileptonic/production/weights.py`**: `weights` producer (MC only), calls
  `electron_weights`, `muon_weights`, `pu_weight`, `normalization_weights` (all stock
  columnflow, config objects were already ready), plus `gen_parton_top` +
  `top_pt_weight` for `is_ttbar` datasets. `mc_weight` itself is **not** called here
  (unlike mttbar) -- it's already computed inside the `default` *selector*
  (`cf.SelectEvents`), not the producer chain.
- **New `tt_semileptonic/production/gen_top.py`**: `gen_parton_top` (parton-level top
  quarks from `GenPart`, needed before showering) + `top_pt_weight` (`sqrt(SF(pt_t) *
  SF(pt_tbar))`, `SF(pt) = exp(a + b*pt)` from `cfg.x.top_pt_reweighting_params`,
  Run 2 TWiki TOP-16-008 recipe -- ported from `mtt/production/gen_top.py`, trimmed to
  just what the weight chain needs (mttbar's `gen_top_decay_products` isn't ported).
- **New `tt_semileptonic/production/default.py`**: top-level producer `law.cfg`'s
  `production_modules` already (previously incorrectly) referenced; currently just
  wraps `weights`.
- **New `tt_semileptonic/production/btag.py`**: `btag_weight_stub` -- a deliberate
  placeholder, not a real b-tag SF. Writes a flat `btag_weight = 1` and is **not**
  added to `cfg.x.event_weights`, so it has zero effect on the combined weight today.
  Why a stub instead of the real thing: columnflow's stock `btag_weights`
  (`columnflow/production/cms/btag.py::btag_weights_post_init`) unconditionally
  overwrites `self.btag_uncs` with a hardcoded Run-2-era systematic-name set (`hf`,
  `lf`, `hfstats1`, ...), running *after* `.derive()`, so it silently clobbers
  mttbar's `upart_btag_weights = btag_weights.derive(..., cls_dict={"btag_uncs":
  ...})` pattern. Confirmed by decompressing the already-fetched
  `btagging_preliminary.json.gz`: the real 2024 `UParTAK4_kinfit` correction set's
  systematic categories are `fsrdef`/`hdamp`/`isrdef`/`jer`/`jes`/`mass`/`statistic`/
  `tune` -- calling `btag_weights` unmodified would raise a correctionlib lookup
  error on `up_hf`, which doesn't exist in the file. Proper fix needs a producer that
  fully overrides `.post_init` (not just the class attribute); swapping the stub for
  it later is a one-line import change in `weights.py`.
- **`config_helper.py`**: fixed `dataset.has_tag("is_ttbar")` (was checking a tag that
  was never assigned to any dataset -- see next item -- so `top_pt_weight` was never
  actually registered in any dataset's `event_weights`, silently).
- **`datasets_helper.py`**: coalesced the ttbar dataset tags. Was
  `{"has_top", "has_ttbar", "is_sm_ttbar"}` (mttbar's three-tier scheme, needed there
  to distinguish SM ttbar from BSM ttbar-resonance samples that also carry
  `has_ttbar`); since this analysis has no BSM ttbar-resonance datasets, simplified to
  `{"has_top", "is_ttbar"}`. `has_ttbar` was dead weight anyway -- nothing ever read
  it.
- **`defaults_and_groups_helper.py`**: `default_producer` (`None` → `"default"`) and
  `default_hist_producer` (`"cf_default"` → `"all_weights"`), so `cf.ProduceColumns`
  and `cf.CreateHistograms` run the new chain without needing explicit
  `--producers`/`--hist-producer` flags.

Not yet run end-to-end (`cf.ProduceColumns` / `cf.CreateHistograms` haven't been
exercised at all in this project yet -- `cf.ReduceEvents` is still the next task per
AGENTS.md).

---

## Tight AK4/AK8 jet ID

`Jet.jetId` / `FatJet.jetId` are absent/unreliable in 2024 nano v15 (known JME bug,
see the twiki/cms-talk links cited in `columnflow.production.cms.jet`'s docstring:
recomputation via correctionlib is the recommended fix, not trusting the stored
NanoAOD bit). The config side (`cfg.x.jet_id` / `cfg.x.fatjet_id`, the `jet_id`
external file) was already in place, just unused.

- `selection/jets.py::jet_selection`: calls `columnflow.production.cms.jet.jet_id`,
  ANDs `(Jet.jetId & 2 == 2)` ("Tight" WP) into the baseline `jet_mask`.
- `selection/fatjets.py::top_tagged_jets`: same with `fatjet_id`, ANDed into
  `toptag_mask` only (not the baseline `fatjet_mask`) -- mirrors mttbar's split.
- Both `.init` functions now declare `jet_id`/`fatjet_id` in `uses`/`produces`.
- `selection/default.py`: `jet_selection` / `top_tagged_jets` added to the top-level
  `default` selector's `produces` set (not just `uses`) -- they now write real columns
  (`Jet.jetId` / `FatJet.jetId`) via the nested producers, not just selection steps,
  so they must be listed there for those columns to be kept.

Not yet re-run to confirm (previously `cf.SelectEvents` ran clean on MC before this
change).

---

## Selection parameters: DotDict → dataclasses

`cfg.x.lepton_selection` / `jet_selection` / `met_selection` / `lepton_jet_iso` were
plain `DotDict.wrap({...})` nested dicts -- no schema, silent `AttributeError` on a
typo, no autocomplete. Confirmed first that `DotDict` isn't required by
columnflow/order anywhere (`order.mixins.AuxDataMixin`'s `cfg.x` proxy just does
`get_aux`/`set_aux` by string key on `self._aux`, agnostic to the stored value's
type), so swapping the value type is purely an analysis-side choice.

- **New `tt_semileptonic/config/selection_params.py`**: frozen dataclasses
  (`LeptonSelectionConfig`, `JetSelectionConfig`, `METSelectionConfig`,
  `LeptonJetIsoConfig`, and their nested pieces) mirroring the exact attribute names
  the selectors already read.
- `config_helper.py`: the four `DotDict.wrap({...})` blocks now construct
  `selection_params.LeptonSelectionConfig(...)` etc. (referenced via the
  `selection_params.` namespace, not bare imports).
- **No changes needed** in `jets.py` / `met.py` / `lepton_jet_2d.py` / `fatjets.py` /
  `production/lepton.py` -- all reads were already plain attribute access
  (`p.column`, `p.min_pt.baseline`, ...), which the dataclasses satisfy identically.
- Caveat: the dataclasses are frozen, so in-place mutation of e.g.
  `cfg.x.jet_selection.ak4.min_pt` (not currently done anywhere) would now raise
  `FrozenInstanceError` instead of silently succeeding.

Verified: `cf.SelectEvents --dataset tt_sl_powheg --version test --calibrators default
--selector default` still runs clean after this change.

---

## Split lepton definition into a producer; move lepton_selection to its own file

The lepton logic that used to be inline in `selection/default.py` is now split:

- **`tt_semileptonic/production/lepton.py::lepton_definition`** (`@producer`, next to
  `lepton_producer`) is the single source of truth for "what is a selected lepton". It
  produces three columns:
  - `Muon.pass_lepton` / `Electron.pass_lepton` — per-object boolean masks (the
    primitive: *which* leptons are good); transient, not kept past `ReduceEvents`.
  - `channel_id` — per-event `int8` label (1 = e, 2 = µ, 0 = neither) derived from those
    masks; kept, because `lepton_producer` and the `cat_1e` / `cat_1m` categorizers
    (which run after `ReduceEvents`) key on it. Redundant with the masks but materialized
    once here on purpose — see the docstring.
  - kinematic cuts live in the module-level `_muon_mask()` / `_electron_mask()` helpers.
- **`tt_semileptonic/selection/leptons.py::lepton_selection`** (moved out of
  `default.py`) is now a thin consumer: calls `self[lepton_definition]`, then builds the
  `"lepton"` step (`channel_id != 0`), the Muon/Electron object index lists, and the
  `n_muon` / `n_electron` aux from the `pass_lepton` masks.
- `selection/default.py` imports `lepton_selection` from `selection/leptons.py` and
  `jet_selection` from `selection/jets.py` (the latter fixing a `NameError` — it was
  referenced but never imported after the jets split).

Behaviour is unchanged; needs a `cf.SelectEvents` run to confirm end to end.

---

## Nuanced, config-driven lepton selection (pt regimes + veto)

`lepton_definition` now implements the m(ttbar)-style lepton definition from the
(previously unused) `cfg.x.lepton_selection.{mu,e}` params, instead of a flat
`pt > 30/35` cut:

- **pt regimes**: low-pt (`tightId` + `pfIsoId >= 4` for muons, `mvaIso_WP80` for
  electrons) vs high-pt (`highPtId == 2` / `mvaNoIso_WP80`), plus the electron
  supercluster-eta cut and barrel-endcap gap veto. New per-event `pt_regime` column
  (0 / 1 / 2).
- **extra-lepton veto**: `Muon.pass_veto_lepton` / `Electron.pass_veto_lepton` from the
  looser `*_addveto` params; `lepton_selection` exposes `VetoMuon` / `VetoElectron`
  object collections and a `dilepton_veto` step (≤ 1 lepton total).
- mask logic lives in `_muon_masks()` / `_electron_masks()` helpers; a
  `@lepton_definition.init` declares the config-dependent NanoAOD columns.
- verified the 7 ID/iso branches exist in the 2024 nano v15 files.

Not done yet: triggers, 2D lepton-jet isolation, MET selection.

Selector steps are now `lepton, dilepton_veto, jet` — `selector_step_groups["default"]`
in `defaults_and_groups_helper.py` updated to match (a mismatch crashes cutflow tasks).

---

## MET filters + m(ttbar)-style AK4 jet selection

- `selection/default.py`: run `columnflow.selection.cms.met_filters` (config already has
  `cfg.x.met_filters`) → step `METFilters`.
- `selection/jets.py::jet_selection` ported from `mtt/selection/jets.py`, config-driven
  from `cfg.x.jet_selection.ak4`:
  - baseline jets `pt > 30`, `|eta| < 2.5`; `LooseJet` (`pt > 0.1`) collection.
  - `jet` step: ≥ 2 baseline jets with **channel-dependent** leading/subleading pt
    (e: 50/40, µ: 50/50).
  - `bjet` step: ≥ 1 b jet (UParT AK4 medium WP, 0.1272); `BJet` / `LightJet`
    collections.
  - `@jet_selection.init` declares the config-named b-tagger branch, plus the full
    `pt/eta/phi/mass` — events are read with NanoAOD vector behavior, so `events.Jet.pt`
    only works when the whole Lorentz vector is present (same for Muon/Electron in
    `lepton_definition`).
  - runs **after** `lepton_selection` (leading-jet pt cut needs `channel_id`).
  - **jet ID not applied yet** — `Jet.jetId` is absent from 2024 nano v15 and needs
    `columnflow.production.cms.jet.jet_id` + the JME correction file, which is deferred
    with the rest of the corrections infrastructure.
- Selector steps now `METFilters, jet, bjet, lepton, dilepton_veto`;
  `selector_step_groups["default"]` + labels updated to match.

---

## MET selection

`selection/met.py::met_selection` (own file — MET is not a jet), ported from
`mtt/selection/jets.py::met_selection`, config-driven from `cfg.x.met_selection`:
channel-dependent `PuppiMET.pt` cut (> 60 GeV e / > 70 GeV mu) -> step `met`. Runs after
the lepton selection (`channel_id`). `@met_selection.init` requests `PuppiMET.{pt,phi}`
(pt alone fails the NanoAOD vector check).

Selector steps: `METFilters, lepton, dilepton_veto, jet, bjet, met`.

---

## Jet-lepton cleaning + lepton-jet 2D cut

**Bug found:** NanoAOD's anti-kt clustering turns an isolated lepton into its own PF
jet, so `jet_selection` was counting the selected lepton as a jet (≈100% of
single-lepton events; verified `min ΔR(lepton, jet) ≈ 0.01`). mttbar removes these in a
`jet_lepton_cleaner` calibrator we haven't ported.

- `production/lepton.py`: `selected_lepton_jet_mask()` helper — per-jet bool, `True` when
  the jet is the selected lepton, via `Jet.{muon,electron}Idx1/2` matched to the
  `pass_lepton` index. `lepton_jet_match_columns` names the NanoAOD branches it needs.
- `selection/jets.py`: exclude `selected_lepton_jet_mask` from `loose`/`baseline`/`b`/
  `light` jet collections. Fixes the jet count; **efficiency changes again**.
- `selection/lepton_jet_2d.py` (new): `lepton_jet_2d_selection`, ported from
  `mtt/selection/jets.py`. `ΔR(lepton, closest pt>15 jet) > 0.4` OR
  `pt_rel > 25 GeV`, applied only for `pt_regime == 2` (high-pt leptons, no isolation in
  their ID). Reads `cfg.x.lepton_jet_iso`. Step `lepton_jet_2d`. Uses the NanoAOD vector
  behavior directly (`metric_table` / `to_Vector3D`) — no `attach_coffea_behavior` call.
- Selector steps now `METFilters, lepton, dilepton_veto, jet, bjet, met, lepton_jet_2d`.

Verified on real events: without cleaning the 2D cut rejects ~100%; with cleaning
`min ΔR` → ~1.3 and the cut behaves sensibly.

`selected_lepton_jet_mask` de-options the per-event lepton index (`fill_none(..., -1)` +
`has_mu`/`has_e` guards) before broadcasting against the jagged `Jet` array — otherwise
the whole jet list became nullable (`N * option[var * bool]`), which propagated to the
`bjet` step and made `results.event` `?bool` (→ `SelectionResult event mask must be of
type N * bool`).

---

## Apply per-process plot colours + `mc_no_qcd` group

- `config_helper.py`: the `colors` dict was defined but never assigned — added the loop
  that sets `process_inst.color1` / `color2` (plotting reads these). `dy` recoloured from
  yellow to teal so it no longer clashes with `tt_fh`. `dy` / `w_lnu` / `vv` were sharing
  a colour before. `--process-settings` can't set colours (only scale/unstack/label), so
  the config is the only place.
- `defaults_and_groups_helper.py`: `mc_no_qcd` dataset group (21) + process group (7),
  = `mc` minus QCD.

---

## AK8 top tagging + all-hadronic veto

`selection/fatjets.py::top_tagged_jets` (new file), ported from
`mtt/selection/jets.py::top_tagged_jets`, config-driven from `cfg.x.jet_selection.ak8`:

- top-vs-QCD score from the GloParT-v3 categories
  `(TopbWqq + TopbWq) / (TopbWqq + TopbWq + QCD)`, working point 0.821; guarded 0/0.
- top-tagged AK8 jet = `pt > 400`, `|eta| < 2.5`, softdrop mass in `[105, 210]`, score
  above WP.
- **`all_had_veto`** step: reject events with ≥ 2 top-tagged AK8 jets (verified:
  ~0.03% of events). Object collections `FatJet` / `FatJetTopTag` /
  `FatJetTopTagDeltaRLepton`, and `n_toptag` / `n_toptag_delta_r_lepton` aux.
- runs after `lepton_producer` (reads the `Lepton` column for the ΔR-to-lepton cut).
- tight fat-jet ID not applied (`FatJet.jetId` absent from nano v15, needs the JME
  file — same as AK4).
- removed the dead `fatjet_selection` stub from `selection/jets.py`.

Selector steps: `METFilters, lepton, dilepton_veto, jet, bjet, met, lepton_jet_2d,
all_had_veto`.

---

## Work around columnflow cf.PlotCutflow regression (PR #783)

columnflow PR #783 replaced `h[{"category": sum, self.variable: sum}]` in
`cf.PlotCutflow.run` with `select_category_bins(...)`, which reduces only the
`category` axis. The variable axis (`event` by default) is left in place, so the 1D
`plot_cutflow` gets a 2D `(step, <variable>)` histogram and `hist.plot_stack` raises
`NotImplementedError: Please project to 1D before calling plot`. Still present on
columnflow `origin/master`.

Fix entirely in our code (no submodule edit):

- `tt_semileptonic/plotting/cutflow.py`: a `plot_cutflow` wrapper that sums every axis
  except `step`, then calls columnflow's `plot_cutflow`.
- `tt_semileptonic/plotting/__init__` → `__init__.py` (it was not a valid package, so
  nothing under `tt_semileptonic.plotting` could be imported).
- `law.cfg` `[luigi_cf.PlotCutflow] plot_function: tt_semileptonic.plotting.cutflow.plot_cutflow`
  makes it the default (law forwards `[luigi_<family>]` → luigi `[<family>]`; a plain
  `[cf.PlotCutflow]` section is not read by luigi).

Remove all three once columnflow reduces the variable axis itself.

---

## custom_increment_stats: add per-process event counts

`selection/default.py`: `custom_increment_stats` now also writes
`num_events_per_process` and `num_events_selected_per_process` to the stats dict.

`cf.MergeSelectionMasks` runs columnflow's `normalization_weights` producer for MC
(to add the `normalization_weight` column), and its setup reads
`stats["num_events_per_process"]` from the merged selection stats — a `KeyError` there
broke the whole plotting / normalization chain.

Note: existing `cf.SelectEvents` stats files predating this change lack the key and must
be regenerated (`--remove-output cf.CalibrateEvents,a,True`, or delete the
`cf.SelectEvents` + `cf.MergeSelectionStats` output dirs for the dataset).

---

## Trim cutflow / plotting defaults to what currently exists

`defaults_and_groups_helper.py`: two more mttbar-ported defaults referenced things that
don't exist yet, so any cutflow/plotting task that fell back to them crashed. Fixed;
the full m(ttbar)-style config is kept commented above each, with an explanation, to be
re-enabled as the selection grows.

- `default_categories` (and therefore `category_groups["default"]`):
  `["1m", "1e", "1m__0t", …]` → `["incl", "1e", "1m"]`. The `__0t`/`__1t` categories
  don't exist while top-tagging is disabled.
- `selector_step_groups["default"]`:
  `["METFilters", "DileptonVeto", …, "Lepton"]` → `["lepton", "jet"]`. Step names must
  match the `SelectionResult` steps produced by `selection/default.py`
  (`missing_selector_step_strategy = raise` in `law.cfg`). Added `lepton` / `jet`
  labels.

Cutflow plot for MC:

```bash
law run cf.PlotCutflow --version test --calibrators default --selector default \
    --datasets mc --processes default --categories incl --selector-steps lepton,jet
```

`cf.PlotCutflow` merges all `cf.SelectEvents` branches (via `cf.MergeSelectionMasks`),
so `--branch 0` does not apply to it; the `_small` config (2 files/dataset) keeps it
cheap. Needs `cf.SelectEvents` branch 1 for the datasets being plotted.

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
