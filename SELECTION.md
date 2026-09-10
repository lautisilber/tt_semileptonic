# Event selection

Reference for the `default` event selector (`--selector default`), run by
`cf.SelectEvents`. Ported from `mttbar` (`mtt/selection/`), adapted for the 2024
NanoAOD v15 campaign and split into one file per object group.

- [Architecture](#architecture)
- [The `default` selector](#the-default-selector)
- [Steps, in execution order](#steps-in-execution-order)
- [Objects kept for `ReduceEvents`](#objects-kept-for-reduceevents)
- [Columns produced](#columns-produced)
- [Config parameters](#config-parameters)
- [Difficulties overcome](#difficulties-overcome)
- [Not implemented yet](#not-implemented-yet)

---

## Architecture

### Files

| file | contents |
|---|---|
| `selection/default.py` | the exposed `default` selector (orchestrator) + `custom_increment_stats` |
| `selection/leptons.py` | `lepton_selection` — turns the lepton columns into a step + object lists |
| `selection/jets.py` | `jet_selection` — AK4 jets, b-tagging, lepton-jet cleaning |
| `selection/met.py` | `met_selection` — channel-dependent PuppiMET cut |
| `selection/lepton_jet_2d.py` | `lepton_jet_2d_selection` — 2D cut for high-pt leptons |
| `selection/fatjets.py` | `top_tagged_jets` — AK8 top tagging + all-hadronic veto |
| `production/lepton.py` | `lepton_definition` (writes the lepton columns), `lepton_producer` (builds `Lepton`), `selected_lepton_jet_mask` helper |

All are registered through `law.cfg` `selection_modules` / `production_modules`.

### How a columnflow selector works

Each `@selector` is a function `(events, **kwargs) -> (events, SelectionResult)`.
`SelectionResult` has three dicts:

- **`steps`** — `{name: per-event bool mask}`. Every step from every sub-selector is
  combined with a logical AND into the final event decision
  (`results.event = reduce(and_, results.steps.values())` in `default`). The step names
  also drive the cutflow: `cf.PlotCutflow` shows the yield after cumulatively applying
  each step in the order given by `config.x.selector_step_groups["default"]`.
- **`objects`** — `{SourceCollection: {NewCollection: index_array}}`. In `ReduceEvents`,
  each `NewCollection` is created by applying `index_array` to `SourceCollection`
  (e.g. `objects["Jet"]["BJet"]` → a new `BJet` collection). The masks are **not**
  applied during `SelectEvents` — only recorded.
- **`aux`** — free-form extras carried on the result (`results.x.<key>`), e.g. per-event
  multiplicities. Not persisted unless explicitly used.

Sub-selectors/producers are invoked via `self[sub](events, **kwargs)` and must be listed
in the caller's `uses=` (and `produces=` if their columns should survive). `@sub.init`
functions add config-dependent column dependencies once `self.config_inst` is known.

### Where it sits in the task graph

```
GetDatasetLFNs → CalibrateEvents → SelectEvents → MergeSelectionMasks → ReduceEvents → …
                                        │
                                        ├── results_*.parquet   the step masks
                                        ├── columns_*.parquet    channel_id, pt_regime,
                                        │                        mc_weight, category_ids, …
                                        └── stats_*.json         counts + weight sums
```

`SelectEvents` does **not** drop events or objects; it records the decision. `ReduceEvents`
(downstream) applies `results.event` and the `objects` index lists, keeping only the
columns listed in `config.x.keep_columns["cf.ReduceEvents"]`.

---

## The `default` selector

`selection/default.py::default`, body order:

```
1.  met_filters                     → step  METFilters
2.  mc_weight            (MC only, adds the corrected generator weight column)
3.  lepton_selection                → steps lepton, dilepton_veto
                                      cols  Muon/Electron.pass_lepton, .pass_veto_lepton,
                                            channel_id, pt_regime
4.  jet_selection                   → steps jet, bjet
5.  met_selection                   → step  met
6.  lepton_jet_2d_selection         → step  lepton_jet_2d
7.  lepton_producer     (builds the Lepton column from channel_id)
8.  top_tagged_jets                 → step  all_had_veto
9.  category_ids         (writes category_ids from the leaf categorizers)
10. results.event = AND of all steps
11. process_ids          (writes process_id)
12. custom_increment_stats  (fills stats_*.json)
```

### Why this order

- **`lepton_selection` before everything channel-dependent.** It writes `channel_id`
  (1 = e, 2 = µ, 0 = neither) and `pt_regime`. `jet_selection` (leading-jet pt cut),
  `met_selection` (MET cut) and `lepton_jet_2d_selection` all branch on `channel_id`, so
  they must run after it. Getting this wrong gives
  `'jet_selection' did not receive any columns matching: channel_id`.
- **`lepton_producer` before `top_tagged_jets`.** The all-hadronic-veto selector needs
  the merged `Lepton` collection for the ΔR-to-lepton computation.
- **`category_ids` after all steps.** `cat_1e` / `cat_1m` read `channel_id`; the (still
  disabled) `cat_0t` / `cat_1t` would read `cutflow.n_toptag_delta_r_lepton`.

The **cutflow display order** is set separately in
`config/defaults_and_groups_helper.py::set_selector_steps` and is currently
`METFilters, lepton, dilepton_veto, jet, bjet, met, lepton_jet_2d, all_had_veto`. It must
list exactly the steps the selectors produce — `law.cfg` has
`missing_selector_step_strategy: raise`, so a stale entry crashes the cutflow tasks.

---

## Steps, in execution order

### 1. MET filters — step `METFilters`

`columnflow.selection.cms.met_filters`, driven by `config.x.met_filters` (a set of
`Flag.*` NanoAOD branches). The selector ANDs all the flags; `default` assigns the
result to `results.steps.METFilters`. Standard Run-3 recommendation:

```
Flag.goodVertices, Flag.globalSuperTightHalo2016Filter,
Flag.EcalDeadCellTriggerPrimitiveFilter, Flag.BadPFMuonFilter,
Flag.BadPFMuonDzFilter, Flag.hfNoisyHitsFilter, Flag.eeBadScFilter,
Flag.ecalBadCalibFilter
```

No external file needed.

### 2. Lepton definition — `production/lepton.py::lepton_definition`

A `@producer` (not a selector) — the single source of truth for "what is a selected
lepton". Reads `config.x.lepton_selection.{mu,e}` and writes four object columns and two
event columns. `@lepton_definition.init` declares the config-named ID/isolation branches.

**Muon masks** (`_muon_masks`, from `cfg.x.lepton_selection.mu`):

| regime | cuts |
|---|---|
| low-pt | `\|eta\| < 2.4`, `30 < pt ≤ 55`, `pfIsoId ≥ 4` (PFIsoTight), `tightId` |
| high-pt | `\|eta\| < 2.4`, `pt > 55`, `highPtId == 2` (global high-pt) |
| **tight** (signal) | `low_pt OR high_pt` → `Muon.pass_lepton` |
| veto | `\|eta\| < 2.4`, `pt > 25`, `tightId`, **and not** a tight muon → `Muon.pass_veto_lepton` |

Rationale: for low-pt muons the isolation is applied explicitly (`pfIsoId`); for high-pt
muons isolation is **not** applied here — it is replaced by the [lepton-jet 2D cut](#5-lepton-jet-2d-cut--step-lepton_jet_2d).

**Electron masks** (`_electron_masks`, from `cfg.x.lepton_selection.e`):

| regime | cuts |
|---|---|
| η acceptance | `\|eta + deltaEtaSC\| < 2.5` (supercluster η) **and** outside the barrel-endcap gap `1.44 < \|eta\| < 1.57` |
| low-pt | η acceptance, `35 < pt ≤ 120`, `mvaIso_WP80` (MVA ID incl. isolation) |
| high-pt | η acceptance, `pt > 120`, `mvaNoIso_WP80` (MVA ID without isolation) |
| **tight** (signal) | `low_pt OR high_pt` → `Electron.pass_lepton` |
| veto | `\|eta+deltaEtaSC\| < 2.5`, `pt > 25`, `cutBased ≥ 3` (medium), **and not** tight → `Electron.pass_veto_lepton` |

**`channel_id`** (per-event `int8`, kept past `ReduceEvents`):

```
n_muon     = sum(Muon.pass_lepton)
n_electron = sum(Electron.pass_lepton)
channel_id = 2  if n_muon == 1 and n_electron == 0     (muon channel)
           = 1  if n_electron == 1 and n_muon == 0     (electron channel)
           = 0  otherwise
```

Ids come from `cfg.add_channel("e", id=1)` / `("mu", id=2)`. `channel_id` is the compact
event label the rest of the analysis keys on (`lepton_producer`, the `cat_1e`/`cat_1m`
categorizers which run after `ReduceEvents`, plotting splits).

**`pt_regime`** (per-event `int8`, kept): regime of the single signal lepton of the
winning channel — `1` = low-pt, `2` = high-pt, `0` = undefined. Consumed by the 2D cut.

### 3. Lepton selection — `selection/leptons.py::lepton_selection`

A thin consumer. Calls `self[lepton_definition]`, then:

- pt-sorted index lists (`sorted_indices_from_mask`) from the four `pass_*` masks →
  `objects`: `Muon`/`VetoMuon`, `Electron`/`VetoElectron`.
- steps:
  - **`lepton`** = `channel_id != 0` — exactly one signal lepton, in exactly one flavour.
  - **`dilepton_veto`** = `(n_tight + n_veto) ≤ 1` — reject events with any second lepton
    (signal or veto). `n_tight` = signal muons + electrons, `n_veto` = veto muons +
    electrons.
- aux: `pt_regime`, `n_muon`, `n_electron`.

### 4. Jet selection — `selection/jets.py::jet_selection`

Reads `config.x.jet_selection.ak4`. `@jet_selection.init` declares
`Jet.{pt,eta,phi,mass,btagUParTAK4B}` plus the lepton-match columns.

**Lepton-jet cleaning first.** NanoAOD's anti-kt clustering turns an isolated lepton into
its own PF jet. `selected_lepton_jet_mask(events)` returns a per-jet bool that is `True`
when `Jet.{muon,electron}Idx1/2` points at the event's `pass_lepton` lepton; those jets
are removed from **every** jet collection below (`not_lepton = ~mask`).

| collection | mask | purpose |
|---|---|---|
| `LooseJet` | `not_lepton & pt > 0.1` | every real jet (cleanup / MET etc. later) |
| `Jet` (baseline) | `not_lepton & \|eta\| < 2.5 & pt > 30` | the analysis jets |
| `BJet` | baseline `& btagUParTAK4B ≥ 0.1272` (UParT AK4 medium) | b-tagged |
| `LightJet` | baseline `& btagUParTAK4B < 0.1272` | non-b |

Steps:

- **`jet`** = `≥ 2` baseline jets with **channel-dependent** leading/subleading pt: e
  channel `(50, 40)`, µ channel `(50, 50)` GeV. Implemented via
  `ak.pad_none(jet[jet_indices], 2)` then `leading_jets[:, 0/1].pt > threshold`, with
  `ak.fill_none(..., False)` for events with < 2 jets.
- **`bjet`** = `≥ 1` b jet.

aux: `n_jet`, `n_bjet`.

> **Tight jet ID is not applied.** `Jet.jetId` is absent from 2024 NanoAOD v15; it must
> be recomputed by `columnflow.production.cms.jet.jet_id`, which needs a JME correction
> file + `cf.BundleExternalFiles`. Deferred with the rest of the corrections stack.

### 5. Lepton-jet 2D cut — step `lepton_jet_2d`

`selection/lepton_jet_2d.py::lepton_jet_2d_selection`. Reads `config.x.lepton_jet_iso`
(`min_pt: 15`, `min_delta_r: 0.4`, `min_pt_rel: 25`).

Replaces the isolation requirement for **high-pt leptons** (whose ID drops isolation).
For each channel, using the single `pass_lepton` lepton and the `pt > 15`, lepton-cleaned
jets:

```
far      = ΔR(lepton, every jet) > 0.4          (lepton isolated from all jets)
pt_rel   = |p_lep × p_jet_closest| / |p_jet_closest|    (lepton momentum ⟂ to nearest jet)
ch_sel   = far  OR  pt_rel > 25 GeV
```

`pt_rel` uses `lepton.to_Vector3D().cross(jet.to_Vector3D()).p / jet_3d.p`. The per-channel
`ch_sel` is selected by `channel_id`, then:

```
sel = ch_sel   where pt_regime == 2   (high-pt)
    = True     otherwise               (low-pt leptons already isolated; undefined events pass)
```

Uses the NanoAOD vector behavior directly (`metric_table`, `to_Vector3D`) — no explicit
`attach_coffea_behavior` (verified the behavior survives the whole selector chain).

### 6. MET selection — step `met`

`selection/met.py::met_selection`. Reads `config.x.met_selection` (`column: PuppiMET`,
`min_pt: {e: 60, mu: 70}`). `@met_selection.init` requests `PuppiMET.{pt,phi}`.

```
met = PuppiMET.pt > 60   in the e channel
    = PuppiMET.pt > 70   in the µ channel
```

### 7. Lepton column — `production/lepton.py::lepton_producer`

Multiplexes `Muon` / `Electron` into a single per-event `Lepton` Lorentz vector based on
`channel_id` (`== 2` → muon, `== 1` → electron), taking the first lepton, filling
`(0,0,0,0)` when there is none, and attaching `PtEtaPhiMLorentzVector` behavior. Consumed
by `top_tagged_jets` and (later) the ttbar reconstruction.

### 8. AK8 top tagging / all-hadronic veto — step `all_had_veto`

`selection/fatjets.py::top_tagged_jets`. Reads `config.x.jet_selection.ak8`.
`@top_tagged_jets.init` declares `FatJet.{pt,eta,phi,mass,msoftdrop}` + the three tagger
score branches.

**Top-vs-QCD score** (GloParT-v3):

```
score = (globalParT3_TopbWqq + globalParT3_TopbWq)
        / (globalParT3_TopbWqq + globalParT3_TopbWq + globalParT3_QCD)      (0/0 guarded → 0)
toptag = score > 0.821                                                     (GloParTv3 tight)
```

**Top-tagged AK8 jet:** `pt > 400`, `|eta| < 2.5`, `105 < msoftdrop < 210`, `toptag`.

Step:

- **`all_had_veto`** = `sum(toptag_mask) < 2` — reject events with ≥ 2 top-tagged AK8
  jets (all-hadronic ttbar contamination / mis-reconstruction). ~0.03 % of tt→SL events.

`objects`: `FatJet` (`pt > 200`, `|eta| < 2.5`), `FatJetTopTag`,
`FatJetTopTagDeltaRLepton` (top-tagged AK8 jets with `ΔR(fatjet, Lepton) > 0.8`).
aux: `n_toptag`, `n_toptag_delta_r_lepton`.

> Tight fat-jet ID (`FatJet.jetId`) is absent from nano v15 — same situation as AK4.

### 9. Stats — `custom_increment_stats`

Fills `stats_*.json` in place. Plain counts (`num_events`, `num_events_selected`),
**per-process** counts (`num_events_per_process`,
`num_events_selected_per_process` — required by columnflow's `normalization_weights`
producer downstream) and, for MC, the sum of `mc_weight` for all and for selected events,
inclusive and per process id.

---

## Objects kept for `ReduceEvents`

From `results.objects` (created in `ReduceEvents`, kept per
`config.x.keep_columns["cf.ReduceEvents"]`):

| source | new collections |
|---|---|
| `Muon` | `Muon`, `VetoMuon` |
| `Electron` | `Electron`, `VetoElectron` |
| `Jet` | `Jet`, `LooseJet`, `BJet`, `LightJet` |
| `FatJet` | `FatJet`, `FatJetTopTag`, `FatJetTopTagDeltaRLepton` |

---

## Columns produced

| column | by | kept past ReduceEvents |
|---|---|---|
| `Muon/Electron.pass_lepton` | `lepton_definition` | no (transient) |
| `Muon/Electron.pass_veto_lepton` | `lepton_definition` | no |
| `channel_id` | `lepton_definition` | **yes** |
| `pt_regime` | `lepton_definition` | **yes** |
| `Lepton.*` | `lepton_producer` | **yes** |
| `mc_weight` | `mc_weight` (MC) | **yes** |
| `process_id` | `process_ids` | **yes** |
| `category_ids` | `category_ids` | **yes** |

---

## Config parameters

All in `config/run3/config_helper.py`.

### `cfg.x.lepton_selection`

```python
"mu": {
    "column": "Muon", "max_abseta": 2.4,
    "min_pt": {"low_pt": 30, "high_pt": 55},
    "iso": {"column": "pfIsoId", "min_value": 4},          # PFIsoTight
    "id":  {"low_pt": {"column": "tightId", "value": True},
            "high_pt": {"column": "highPtId", "value": 2}}, # global high-pt
    "min_pt_addveto": 25, "max_abseta_addveto": 2.4,
    "id_addveto": {"column": "tightId", "value": True},
},
"e": {
    "column": "Electron", "max_abseta": 2.5,
    "min_pt": {"low_pt": 35, "high_pt": 120},
    "barrel_veto": [1.44, 1.57],
    "mva_id": {"low_pt": "mvaIso_WP80", "high_pt": "mvaNoIso_WP80"},
    "min_pt_addveto": 25, "max_abseta_addveto": 2.5,
    "id_addveto": {"column": "cutBased", "min_value": 3},  # medium
},
```

### `cfg.x.jet_selection`

```python
"ak4": {
    "column": "Jet", "max_abseta": 2.5,
    "min_pt": {"baseline": 30, "e": [50, 40], "mu": [50, 50]},
    "btagger": {"column": "btagUParTAK4B", "wp": 0.1272},  # UParT AK4 medium
},
"ak8": {
    "column": "FatJet", "max_abseta": 2.5,
    "min_pt": {"baseline": 200, "toptagged": 400},
    "msoftdrop": [105, 210],
    "toptagger": {"column": ["globalParT3_TopbWqq", "globalParT3_TopbWq", "globalParT3_QCD"],
                  "wp": 0.821},                             # GloParTv3 tight
    "delta_r_lep": 0.8,
},
```

### `cfg.x.met_selection` / `cfg.x.lepton_jet_iso`

```python
met_selection = {"column": "PuppiMET", "raw_column": "RawPuppiMET",
                 "min_pt": {"e": 60, "mu": 70}}
lepton_jet_iso = {"min_pt": 15, "min_delta_r": 0.4, "min_pt_rel": 25}
```

---

## Difficulties overcome

Ordered roughly as encountered while building this.

### `channel_id` is not a NanoAOD field

It has to be *produced* by the analysis (from the selected-lepton counts) and written
with `set_ak_column`, before any consumer. Missing it →
`did not receive any columns matching: channel_id`. Now produced by `lepton_definition`.

### `category_ids` runs a categorizer for *every leaf category*

Not just the ones asked for on the CLI. Adding a category whose `@categorizer` reads a
not-yet-produced column breaks `SelectEvents`. This is why the `0t` / `1t` top-tag
categories are still commented out in `config/categories_helper.py` — `cat_0t` / `cat_1t`
read `cutflow.n_toptag_delta_r_lepton`, which the cutflow-features producer (not yet
added) would create.

### Physics-object collections need the full `{pt,eta,phi,mass}` in `uses`

Events are read with NanoAOD (`vector`) behavior. `events.Jet.pt` goes through `vector`,
which raises `array does not have azimuthal coordinates` unless `phi` (and `mass`, for
the 4-vector) were also requested — even when you only cut on `pt`/`eta`. Every
sub-selector's `init` requests the full `{pt,eta,phi,mass}`; `met_selection` requests
`PuppiMET.{pt,phi}`.

### Execution order vs. static column resolution

columnflow's static check (`used_columns` / `produced_columns`) validates the dependency
*graph*, not the call order. It happily accepts a selector reading `channel_id` while the
producer of `channel_id` is elsewhere in the tree — the failure only shows at runtime.
`jet_selection` / `met_selection` / `lepton_jet_2d_selection` must be **called** after
`lepton_selection` in `default`'s body.

### NanoAOD clusters an isolated lepton into its own jet

The AK4 jet collection contains a jet that *is* the selected lepton (`min ΔR ≈ 0.01`,
verified). Consequences: (a) `jet_selection` counted the lepton as a jet; (b) the 2D cut,
which looks for the closest jet to the lepton, always found the lepton itself
(`pt_rel ≈ 0`) and rejected ~100 % of events. `mttbar` removes these in a
`jet_lepton_cleaner` **calibrator** (needs JEC infra). We do the lightweight version:
`selected_lepton_jet_mask` matches `Jet.{muon,electron}Idx1/2` to the selected lepton and
drops that jet from every jet collection. After cleaning, `min ΔR → ~1.3`.

### Nullable-type propagation → `SelectionResult event mask must be of type N * bool`

`ak.firsts(...)` gives a **per-event `?int`** (None when the event has no selected
lepton). Comparing that against the jagged `Jet.muonIdx1` (`N * var * int`) makes the
**whole jet list nullable** — `N * option[var * bool]`. `ak.fill_none(x, False)` does not
fix an outer-level option, so it survived into `jet_mask` → the `bjet` step became
`?bool` → `reduce(and_, steps)` → `results.event` was `?bool`. Fix: de-option the lepton
index first (`ak.fill_none(..., -1)`) and guard with `has_mu` / `has_e` so the `-1`
sentinel can't spuriously match lepton-less jets in the other channel.

### GloParT top-tagger score is 0/0 for soft fat jets

`(TopbWqq + TopbWq) / (TopbWqq + TopbWq + QCD)` → `NaN` when all three scores are ~0.
`NaN > wp` is `False` (harmless for the mask) but noisy. Guarded with a nested `ak.where`.

### Infrastructure issues that shaped the selection

- **XRootD atexit deadlock** — reading input over `root://` hangs the sandbox process at
  exit *after* it finished. Fixed by reading from the DESY dcache POSIX mount
  (`law.cfg` `[local_desy_dcache]` first in `lfn_sources`). See `ISSUES.md`.
- **`cf.PlotCutflow` regression (columnflow #783)** — the variable axis is not reduced;
  worked around with a wrapper plot function. See `ISSUES.md`.
- **`num_events_per_process`** — columnflow's `normalization_weights` (run for MC inside
  `cf.MergeSelectionMasks`) requires this key in the selection stats; `custom_increment_stats`
  now writes it.
- **`selector_step_groups` / `default_categories` / dataset & process groups** — all
  ported from `mttbar` with names that don't exist in this campaign; trimmed to what the
  selection actually produces. A stale `selector_step_groups` entry crashes the cutflow
  tasks (`missing_selector_step_strategy: raise`).

---

## Not implemented yet

| piece | blocker |
|---|---|
| tight AK4 / AK8 jet ID | `Jet.jetId` / `FatJet.jetId` absent from nano v15 → need `columnflow.production.cms.jet.{jet_id,fatjet_id}` + JME correction file + `cf.BundleExternalFiles` |
| HLT trigger requirement | needs a `cfg.x.triggers` config block; deferred `check_early` (early/late run split) |
| jet energy corrections (JEC/JER) + `jet_lepton_cleaner` | corrections infrastructure |
| cutflow features (`cutflow.*`) | next task — unblocks `cf.PlotCutflowVariables1D` and re-enabling the `0t`/`1t` categories |
| gen-level features (`gen_parton_top`, `gen_v_boson`) | reduction / production step |
| data selection | `SelectEvents` currently fails on `data_*` datasets (undiagnosed; also no golden-JSON / lumi filter) |
