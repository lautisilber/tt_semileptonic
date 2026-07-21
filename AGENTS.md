# AGENTS.md: tt_semileptonic Workflow Guide

This repository implements a tt_bar + jets analysis using Columnflow (Law-based framework). Patterns documented below are specific to `tt_semileptonic` and should **not** be copied verbatim—adapt the structure to your use case.

---

## Directory Structure

```
tt_semileptonic/
├── tasks/                 # Task orchestration files (via law.cfg)
│   ├── base.py            # Custom BaseTask with task_namespace="tt_semileptonic"
│   ├── config.py          # Config processing
│   └── reduction.toml     # Reduction workflow definitions
├── selection/             # @selector functions (muons, jets definition)
│   └── example.py         # muon_selection(), jet_selection()
├── categorization/        # @categorizer functions (process categories)
│   └── example.py         # cat_incl(), cat_2j() etc.
├── calibration/           # @calibrator for JEC smearing
│   └── example.py         # jet_jec_calibrator()
├── production/            # Producers (observable extraction)
│   └── example.py         # jet_features() producing {ht, n_jet, dijet.*}
├── inference/             # ML model definitions (@dnnmodel)
│   └── example.py         # DNN model with categories/processes defined
├── reduction/             # @reducer functions (column addition)
│   └── example.py         # bbbar_features() adding Jet.from_b_hadron
├── plotting/              # Custom plot functions
│   └── example.py         # plot_*_distribution() helpers
└── config/                # Columnflow config objects & store parts
    └── run3/
        └── analysis_tt_semileptonic.py  # Main Analysis object
```

---

## Core Patterns by Pattern Type

### **PRODUCERS** (`@producer @classmethod`)
Used to extract observables from events. Use `uses=` for inputs, `produces=` for outputs.

```python
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask
from law.config_groups.producer import producer

@producer(cls=TT_SEMILEPTONICTask, uses=["{config}"] if config else None)
def my_producer(events, *args):
    """Extract observables from events."""
    cols = {}
    
    # Extract single jets
    jets = events.Jet  # auto-expanded to {pt, eta, phi, mass}
    pts = [jet.pt for jet in ak.flatten(jets)]
    cols.update(Jet.pt = sum(abs(p) for p in abs(pts)))
    
    # Or with dijets directly (using Jet collection)
    from tt_semileptonic.column_ops import jets_to_dijets
    dijets = jets_to_dijets(jets)  # List of (jet1, jet2) tuples
    cols.update(
        ht=sum(abs(jet.pt) for jet in events.Jet),
        n_ak4_jet=ak.num(events.Jet.pt, axis=1),
        dijets=dijets,  # Auto-expanded to {dijet_mass, dijet_delta_r, dijet_pt}
    )
    
    return cols
```

**Note:** The production example `production/example.py` builds `ht` via list comprehension and pads jets to 2 using `ak.pad_none(events.Jet, 2)` before pairing.

---

### **SELECTORS** (`@selector`)
Define events that pass selection criteria for subsequent steps. Returns `(events, SelectionResult)`.

```python
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask
from law.config_groups.selector import selector

@selector(cls=TT_SEMILEPTONICTask, uses=["{muons}"])
def muon_selection(events):
    """Select signal-like muon definition."""
    muons = events.Muon  # Auto-expanded to {pt, eta, phi, mass}
    
    # Muon selection criteria: pt ≥ 20, |eta| < 2.1, exactly one muon in event
    pass_pt_mask = muons.pt >= 20.0
    pass_eta_mask = np.abs(muons.eta) < 2.1
    n_mu_in_event = ak.num(events.Muon.p, axis=1) == 1
    
    # Combined selection (events mask)
    events_pass = (pass_pt_mask & pass_eta_mask & n_mu_in_event).astype(int)
    
    # Resulting muons after cut
    selected_pt = muons.pt[pass_pt_mask]
    selected_mass = muons.mass[pass_pt_mask & pass_eta_mask]
    
    return events, SelectionResult(
        steps={
            "input": {Muon: "muons"},  # Source columns used
        },
        objects={
           Muon: (selected_pt, selected_eta, selected_phi, selected_mass),  # Tuple per collection key
        }
    )
```

**Note:** The example `selection/example.py` uses `SelectionResult.steps` for cut documentation and returns `(events, SelectionResult)` with both `steps` dict (source mapping) and `objects` dict (post-selection column values).

---

### **CATEGORIZATION** (`@categorizer`)
Define process categories using the current event state. Returns category masks.

```python
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask
from law.config_groups.categorization import categorizer

@categorizer(uses=["{muons}", "{jets}"])  # Input columns for boundary checking
def cat_incl(events):
    """Inclusive category mask."""
    return {events: np.ones(len(events), dtype=np.bool8)}

@categorizer(uses=["{muons}", "Jet.pt"})  # Requires Jet.pt column explicitly
def cat_2j(events, events_Jet_pt=None):
    """Category requiring at least two jets (pt-based)."""
    if events_Jet_pt is not None:
        n_jets = ak.num(events_Jet_pt, axis=1)
    else:
        # Fall back to raw Jet count
        n_jets = ak.num(events.Jet.pt, axis=1)
    
    mask = n_jets >= 2
    
    return {events: mask}
```

---

### **CALIBRATION** (`@calibrator`)
Apply JEC corrections with deterministic seeds and smearing. Returns corrected event columns.

```python
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask
from law.config_groups.calibration import calibrator

@calibrator(uses=["events.Jet"], produces=["{Jet.pt_jec_up, Jet.mass_jec_up, ...}"])
def jet_jec_calibrator(events, seed=42, smearing=None):
    """Apply JEC up/down with deterministic runs."""
    
    # Deterministic seed for ML training stability
    np.random.seed(seed)
    
    if smearing is None:
        smearing = 0.05
    
    # Generate smear factor (1.05 up, 0.95 down, 1.0 nominal)
    def smear(jet):
        jitter = np.random.uniform(1 - smearing, 1 + smearing)
        corrected = jet.pt * jitter
        return {'pt': corrected, 'mass': corrected}
    ```

---

### **ML MODEL** (`class MLModel`)
Define neural networks for classifier/regression. Use `Route | str` types for inputs/outputs.

```python
from ctapike.ml.models import DNNModel
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask
from law.config_groups.inference import dnnmodel

class MyDNNModel(DNNModel):
    """DNN classifier for signal/background discrimination."""
    
    single_config = True
    
    uses = (str, str)  # e.g. ("Jet.pt", "Muon.pt")
    produces = (str,)   # e.g. ("response:",)
    
    training_calibrators = (jet_jec_calibrator,)  # Apply before training
    training_selecs = (muon_definition_, jet_definition_)  # Required for training
    
    def config(self, inputs, outputs, task):
        """Configure network architecture."""
        return DNNModel(
            name="DNN_tt_2024",
            hidden_layers=3,
            activation="relu",
        )
    
    def predict(self, events, config_inst, category_inst):
        """Forward pass through DNN."""
        from tt_semileptonic.column_ops import jets_to_dijets
        dijets = jets_to_dijets(events.Jet)
        
        inputs_dict = {"dijet_mass": [d[0].mass * d[1].mass for d in dijets]}
        return super().predict(inputs_dict, config_inst=..., yaxis=None)

# Process and category configuration (from example.py)
class DNNModelConfig(MLModel.config):
    class incl:  # For inclusive category
        processes = ["ST"]
        parameters = {"luminosity_unc": 0.9317, "inv_lum_unc": 0.9826}
    
    class ttbar_cat:  # For TT-bar category (TT):
        pass  # Inherits same structure as above
```

**Critical:** Model configuration via `processes=` lists and `parameters=` dict for uncertainty terms in `tt_semileptonic/inference/example.py` style.

---

### **PLOT FUNCTIONS**
Custom plot functions receive `(hists, config_inst, category_inst, variable_insts, style_config, yscale, process_settings, ...)`.

```python
from matplotlib import pyplot as plt
from tt_semileptonic.plotting.helper import (
    apply_variable_settings,
    remove_residual_axis,
    add_uncertainty_envelope
)

def plot_dijet_mass(hists, config_inst, category_inst, var="dijet_mass", yscale=None):
    # Helper: normalize histogram for normalization histograms
    hists_norm = remove_residual_axis(hists=vars(), dim="event")
    
    # Add statistical uncertainties
    fig, ax = plt.subplots()
    plot_data = hists_norm[hists_norm.process]  # Get specific process
    
    # Apply columnflow helper for settings
    style_config = apply_variable_settings(
        variables=dict(dijet_mass={"min": 0.0})
    )
    
    return fig, ax

def plot_with_uncertainties(hists, config_inst, category_inst, var, yscale):
    # Plot with luminosity uncertainties and jet energy scale variations
    from tt_semileptonic.column_ops import add_jes_syst
    
    return fig, ax
```

---

## Configuration Hierarchy

### Columnflow Config (`config.py`)
- Define config objects for each analysis node
- Include: sandboxes, input stores, hooks (reducer, categorization)
- Example structure:

```python
class MyAnalysis(Analysis):
    # Sandbox declarations
    sandbox = "bash"  # Or "cmssw", "columnflow_bash"
    sandbox_mwsf = "bash"  # For event weighting
    
    # Store parts (input/output stores)
    class store_parts:
        input = {"Muon": [1]}
        output = {"Jet_features": ["output"], "dijet_features": ["output"]}
    
    # Hooks: which modules run where
    hist_hooks = [
        ("hist_reducer", 0, lambda events: create_histograms(events)),
    ]
```

---

## Setup & Execution

### Environment Setup (from `setup.sh`)
Source before running tasks:
```bash
source /data/dust/user/lsilberg/columnflow/tt_semileptonic/modules/columnflow/setup.sh 2>/dev/null \
    || source "${CF_SETUP_SCRIPT:-/path/to/setup.sh}"

export TT_SEMILEPTONIC_BASE=/data/dust/user/lsilberg/columnflow/tt_semileptonic
export TT_SEMILEPTONIC_SETUP="$(pwd)"

# Run workflow
law start -w tt_semileptonic/tasks/reduction.toml
```

### Law Module Definitions (`law.cfg`)
Module declarations go at `/project_root/law.cfg`. Include:
- Custom task modules (`tt_semileptonic.tasks`)
- Columnflow standard modules (columnflow.core, columnflow.column_ops)
- cmsdb campaign infrastructure for CMSSW sandbox

---

## Key Dependencies

```python
# core law utilities
from tt_semileptonic.tasks.base import TT_SEMILEPTONICTask

# Columnflow operations
from columnflow.column_ops import (
    ak,  # Array manipulation
    jets_to_dijets,     # Pairing logic
    add_jes_syst        # JES uncertainties
)

# cmsdb infrastructure
import cmsdb
from cmsdb.campaigns.run3.config import (
    ColumnflowConfig,  # Base config class
    StoreParts         # For input/output store setup
)

# Linter configs
# .flake8: max-line-length=120, ignore E128,E306,E402,E722,E731,W504,Q003
```

---

## Pattern-Specific Implementation Notes

### Selection Result Structure
All selectors return `(events, SelectionResult)` with:
- `steps`: dict of `{source_name: source_type}` (e.g., `{"Muon": "muons"}`)
- `objects`: tuple of column values ordered by collection order (e.g., `(pt, eta, phi, mass)`)

### Categorization Boundaries
Categories return dict: `{events: mask}`, where mask is bool array indicating pass events. Multiple boundaries in one categorizer allowed via separate function or multiple returns.

### Store Parts Pattern
Use `@store_parts` for columnflow input/output store configuration:
```python
class StoreParts(StorePartGroup):
    from = {"Muon": ["input_store"]}  # Source path
    to   = {"Jet_features": ["output_store", "reducer_output"]}  # Target paths
    # Optional: exclude=, modifiers= for filtering/editing before writing
```

---

## Testing Checklist

- [ ] All `@decorator` functions return expected types (SelectionResult, dict, cat mask)
- [ ] Config objects declare sandboxes correctly (bash vs cmssw)
- [ ] Store parts include all inputs/outputs for input/output store setup
- [ ] Histogram hooks define proper `(config_group_id, hook_type)` pairs
- [ ] MLModel uses correct `uses=` / `produces=` tuple types (Route|str)
- [ ] Law modules registered in `law.cfg` at project root level

---

## Common Pitfalls to Avoid

1. **Don't** copy example patterns verbatim—use as structural guides only
2. **Remember**: `SelectionResult` requires both `steps` and `objects` dict keys
3. **Check**: Store parts need explicit `from=` (source) and `to=` targets (destinations)
4. **Verify**: MLModel classes must use `Route | str` type annotations, not raw strings
5. **Note**: Law modules are declared in top-level `law.cfg`, not per-file imports
