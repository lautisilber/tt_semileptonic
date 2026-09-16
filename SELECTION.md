# Selection — tt_semileptonic

Detailed, ordered description of every calibration step, filter, cut, and selection
applied to an event, from the raw NanoAOD input through `cf.ReduceEvents`. Task order:

```
cf.CalibrateEvents  ->  cf.SelectEvents  ->  cf.ReduceEvents
(calibration/default.py)  (selection/default.py)  (cf_default reducer)
```

`cf.CalibrateEvents` corrects object 4-vectors (jets, MET) but rejects no events.
`cf.SelectEvents` computes per-event/per-object boolean masks (it does not remove
anything from the array itself) and assigns categories. `cf.ReduceEvents` is where
events actually get dropped — it applies the combined mask computed in `cf.SelectEvents`
and builds the final, trimmed set of columns and object collections used downstream.

---

## 1. Calibration (`cf.CalibrateEvents`, `calibration/default.py`)

Run in this order:

### 1.1 `mc_weight`
MC only. Writes a per-event `mc_weight` column: the sign of the generator weight
(`genWeight`), used to correct for MC samples with negative-weight events.

### 1.2 `deterministic_seeds`
Writes a per-event `deterministic_seed` and a per-jet `Jet.deterministic_seed`, derived
from run/luminosity-block/event numbers so that random-number-dependent corrections
(e.g. JER smearing) are reproducible across re-runs. The per-jet seed is currently
produced but not yet wired into JER's smearing (JER uses its default event-based random
generator instead, see §1.4).

### 1.3 `jet_lepton_cleaner`
Corrects AK4 jet 4-vectors for lepton contamination. For any electron or muon whose PF
candidates were clustered into a jet (identified via `Jet.{muon,electron}Idx1/2` — *any*
matched lepton, not only the one signal lepton chosen later in selection), the lepton's
4-vector is subtracted from the jet's 4-vector, provided the result passes three sanity
checks:
- the cleaned jet mass stays non-negative (within a small numerical tolerance),
- the angle between the original and cleaned jet directions doesn't change by more than
  90° (relaxed to any change if the cleaned jet's pt drops below 10 GeV, since a jet that
  is almost entirely the lepton can flip direction on cleaning due to resolution effects),
- the lepton's energy is compatible (within 10%) with the jet's charged-EM (electron) or
  muon (muon) PF energy fraction.

Before cleaning, NanoAOD's own default jet energy correction is undone (`Jet.rawFactor`
reset to 0), so the subsequent JEC (§1.4) computes its correction starting from the
lepton-subtracted raw jet.

### 1.4 `jet_energy` (JEC + JER)
Run in this order: **AK4 JEC → AK4 JER → AK8 JEC → AK8 JER** (AK4 is fully corrected,
including its own MET propagation, before AK8 is touched; AK8 does not repeat MET
propagation).

- **JEC** (jet energy correction): corrects `Jet.pt`/`Jet.mass` (and, for AK4,
  `PuppiMET.pt`/`.phi` via type-1 MET propagation) for pileup offset (L1FastJet),
  non-linear detector response (L2Relative, L3Absolute), and residual data/MC differences
  (L2L3Residual). 2024 campaign `Summer24Prompt24`, version `V2`, jet type `AK4PFPuppi`
  (AK4) / `AK8PFPuppi` (AK8).
- **JER** (jet energy resolution smearing, MC only): smears MC jet pt to match the
  measured data resolution (gen-jet-matched where possible, otherwise stochastic). No
  official 2024 JER corrections exist yet; the 2023 post-BPix campaign
  (`Summer23BPixPrompt23_RunD`) is used as a fallback.
- Only the **nominal** correction is currently applied for both JEC and JER — no
  uncertainty-shifted variations are produced yet, even though the corresponding
  `jec_Total_up/down` / `jer_up/down` shifts are already defined in the config.

---

## 2. Selection (`cf.SelectEvents`, `selection/default.py`)

Selector steps, in the order they run. Each step contributes a boolean mask; an event
survives only if **all** steps' masks are `True` (the final AND is computed once, after
every step below has run — see §2.13).

### 2.1 MET filters — step `METFilters`
Standard data-quality event flags (rejects instrumental noise / reconstruction failures):
`Flag.goodVertices`, `Flag.globalSuperTightHalo2016Filter`,
`Flag.EcalDeadCellTriggerPrimitiveFilter`, `Flag.BadPFMuonFilter`,
`Flag.BadPFMuonDzFilter`, `Flag.hfNoisyHitsFilter`, `Flag.eeBadScFilter`,
`Flag.ecalBadCalibFilter`. All must be `True`. Applied to both data and MC.

### 2.2 Golden JSON — step `JSON` (data only)
Keeps only events from certified-good luminosity blocks (the standard "good runs" lumi
mask). No MC equivalent — simulation has no runs/luminosity blocks to certify.

### 2.3 `mc_weight` (MC only)
The same sign-of-`genWeight` correction as §1.1 is computed again here (both the
calibration-stage and this selection-stage `mc_weight` calls currently coexist in the
code).

### 2.4 Lepton selection — steps `lepton`, `dilepton_veto`
The single source of truth for what counts as a good lepton (used for both electrons and
muons, symmetrically):

- **Two pt regimes**, each with its own identification criteria:
  - **Low-pt**: muon `30 < pt <= 55` GeV with `tightId` + `pfIsoId >= 4` (PFIsoTight);
    electron `35 < pt <= 120` GeV with `mvaIso_WP80`.
  - **High-pt**: muon `pt > 55` GeV with `highPtId == 2` (global high-pt, includes
    tracker high-pt); electron `pt > 120` GeV with `mvaNoIso_WP80`.
  - A per-event `pt_regime` column (0 = none, 1 = low-pt, 2 = high-pt) records which
    regime the event's signal lepton falls into.
- **Kinematic acceptance**: muon `|eta| < 2.4`; electron `|eta_SC| < 2.5`
  (supercluster eta = `eta + deltaEtaSC`) with the barrel-endcap transition region
  `1.44 < |eta| < 1.57` excluded.
- **Extra-lepton veto**: a looser definition (muon `pt > 25`, `tightId`, `|eta| < 2.4`;
  electron `pt > 25`, `cutBased >= 3` (medium), `|eta_SC| < 2.5`) identifies additional
  leptons that are *not* the signal lepton. Step `dilepton_veto` requires at most one
  lepton total (signal + veto combined) across both flavors.
- Step `lepton` requires exactly one signal lepton of a single flavor
  (`channel_id != 0`); `channel_id` is `1` for electron, `2` for muon, `0` otherwise.
- Produces `VetoMuon`/`VetoElectron` object collections (the veto leptons) alongside the
  signal `Muon`/`Electron` index lists used by `cf.ReduceEvents`.

### 2.5 Jet selection (AK4) — steps `jet`, `bjet`
- **Lepton-jet overlap removal**: the analysis jet's own PF-clustered signal lepton (via
  `Jet.{muon,electron}Idx1/2` matched to the one selected signal lepton) is excluded from
  every jet collection below.
- **Loose jets**: `pt > 0.1` GeV (keeps essentially all real jets, filters out
  cleaned/degenerate ones).
- **Baseline jets**: `pt > 30` GeV, `|eta| < 2.5`, and passing the **tight jet ID**
  (recomputed from correctionlib rather than trusting the stored NanoAOD `jetId` bit,
  which is unreliable in recent NanoAOD versions).
- Step `jet`: at least two baseline jets, with **channel-dependent** leading/subleading
  pt thresholds — electron channel `50`/`40` GeV, muon channel `50`/`50` GeV.
- **b-tagging**: baseline jets are split into `BJet` (b-tagged) / `LightJet` (not) using
  the UParT AK4 discriminant (`btagUParTAK4B`) at the medium working point (`0.1272` for
  2024 — currently a placeholder value pending official calibration). Step `bjet`:
  at least one b-tagged jet.

### 2.6 MET selection — step `met`
Channel-dependent missing transverse momentum cut on `PuppiMET.pt`: `> 60` GeV in the
electron channel, `> 70` GeV in the muon channel.

### 2.7 Lepton-jet 2D isolation — step `lepton_jet_2d`
Applies only in the **high-pt** lepton regime (`pt_regime == 2`), where the standard
isolation requirement is absent from the lepton ID; passes everything else through
unconditionally. Requires, for the selected lepton relative to the nearest jet with
`pt > 15` GeV (excluding the lepton's own jet):

```
delta_r(lepton, closest jet) > 0.4   OR   pt_rel(lepton, jet) > 25 GeV
```

where `pt_rel` is the magnitude of the lepton's momentum component perpendicular to the
jet axis.

### 2.8 Lepton collection merge
Not a cut — builds a single `Lepton` column per event by selecting either the signal
`Muon` or `Electron` based on `channel_id`, so downstream steps (top-tagging ΔR, cutflow
features) can refer to "the lepton" without branching on flavor.

### 2.9 AK8 top tagging + all-hadronic veto — step `all_had_veto`
- **Top-tag score**: computed from three GloParT-v3 categories,
  `(TopbWqq + TopbWq) / (TopbWqq + TopbWq + QCD)` (guarded against 0/0).
- **Baseline AK8 jets**: `pt > 200` GeV, `|eta| < 2.5`.
- **Top-tagged AK8 jets**: `pt > 400` GeV, `|eta| < 2.5`, softdrop mass in
  `[105, 210]` GeV, top-tag score above the working point (`0.821` for 2024 — currently a
  placeholder value pending official calibration), and passing the tight AK8 jet ID
  (recomputed, same reasoning as AK4 in §2.5).
- A further **lepton-separated** top-tagged subset additionally requires
  `delta_r(fat jet, Lepton) > 0.8` (events without a `Lepton` pass this automatically) —
  this is the count actually used by the `0t`/`1t` categories (§2.11).
- Step `all_had_veto`: fewer than two top-tagged AK8 jets in the event.
- Produces `FatJet` (baseline), `FatJetTopTag`, and `FatJetTopTagDeltaRLepton` object
  collections.

### 2.10 Jet veto map — step `jet_veto_map`
Applied to **both** data and MC. Rejects events containing an AK4 jet in a detector
region flagged as bad for the given data-taking period (dead/noisy calorimeter towers,
timing issues). Jets are pre-selected for this check with `pt > 15` GeV, a PF EM-energy
fraction cut (`chEmEF + neEmEF < 0.9`), and the tight-with-lepton-veto jet-ID bit
(Run 3 convention); jet eta/phi are clipped into the correction map's valid input domain
(`|eta| <= 5.19`, `|phi| <= pi`) before evaluation. Produces a per-jet
`Jet.veto_map_mask` column in addition to the event-level step.

### 2.11 QCD spikes — step `QCDSpikes` (QCD MC only)
Applied only to datasets tagged `is_qcd`. HT-binned QCD MC is prone to a mismeasurement
pathology where a single jet is reconstructed with more pt than the generator-level
hard-scatter energy scale can account for. Rejects events where the leading jet's pt
exceeds the event's generator-level `LHE.HT`.

### 2.12 Cutflow features
Not a cut — writes bookkeeping columns (under the `cutflow.*` namespace) used for
cutflow plotting and by the `0t`/`1t` categorizers: per-rank pt/eta for the four leading
jets and fat jets, the leading lepton's pt/eta, object counts (`n_jet`, `n_bjet`,
`n_lightjet`, `n_toptag`, `n_toptag_delta_r_lepton`, `n_muon`, `n_electron`), and
generator-level `LHE.HT` for non-diboson MC.

### 2.13 Categorization
Not an event-rejecting cut — assigns each event to one or more analysis categories
(`category_ids` column), computed from the columns produced above:
- `incl` — every event (fully inclusive).
- `1e` / `1m` — electron / muon channel (`channel_id`).
- `0t` / `1t` — zero / exactly one top-tagged AK8 jet, using the lepton-separated count
  from §2.9 (`cutflow.n_toptag_delta_r_lepton`); `0t` corresponds to the *resolved*
  topology (top decay products captured as separate AK4 jets), `1t` to the *boosted*
  topology (a full top decay captured in one AK8 jet).
- Combined categories (`1e__0t`, `1m__1t`, etc.) are generated automatically from the
  `lepton` × `n_top_tags` category groups.

### 2.14 Combined event selection
All boolean masks from steps §2.1–§2.11 (`METFilters`, `JSON` if data, `lepton`,
`dilepton_veto`, `jet`, `bjet`, `met`, `lepton_jet_2d`, `all_had_veto`, `jet_veto_map`,
`QCDSpikes` if QCD MC) are combined with a logical AND into the final per-event selection
decision. This is the mask `cf.ReduceEvents` applies (§3).

### 2.15 Process IDs and stats bookkeeping
Not cuts — `process_ids` tags each event with the physics process it belongs to (for
per-process plotting/normalization); a custom stats step accumulates per-process event
counts and summed MC weights (before and after selection) into the task's stats output,
used later by the normalization-weight calculation.

---

## 3. Reduction (`cf.ReduceEvents`)

Applies the combined mask from §2.14 (events failing any selection step are dropped),
then builds the final object collections referenced above (`BJet`, `LightJet`,
`LooseJet` from `Jet`; `FatJetTopTag`, `FatJetTopTagDeltaRLepton` from `FatJet`;
`VetoMuon`/`VetoElectron` from `Muon`/`Electron`) as new columns alongside their sources.
Finally trims the event array down to a configured set of columns — the calibrated
physics-object kinematics, generator-level information (MC), and the derived columns
produced during selection (`channel_id`, `pt_regime`, `category_ids`, `process_id`,
`mc_weight`, `cutflow.*`, the `Lepton` collection, etc.) — discarding everything else.

---

## Known caveats

- **b-tag working point** (`0.1272`, UParT AK4 medium) and **top-tag working point**
  (`0.821`, GloParT-v3 tight) are both explicitly marked as placeholder values in the
  config, pending official 2024 calibration.
- **JER** falls back to the 2023 post-BPix campaign; no 2024 JER corrections exist yet.
- **JEC/JER uncertainty variations** are not yet produced — only nominal corrections run.
- **No trigger requirement** is applied anywhere in the selection.
- **MET-φ (xy) correction** is not applied — the necessary 2024 correction file has not
  yet been published by JME.
- `mc_weight` is computed twice (once in calibration, once in selection) with identical
  logic; both calls currently coexist.
