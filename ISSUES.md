# Known framework issues

Problems that originate in **columnflow** (or its sandbox environment) rather than in
this analysis, documented here so that someone with deeper framework knowledge can
evaluate and hopefully fix them upstream. Each entry records what we observed, the
root cause as far as we traced it, and the local workaround currently in place.

Environment for all entries below:

| | |
|---|---|
| columnflow | `v0.3.0-328-g51cced36` (submodule pinned; bug also present on `origin/master`, then ~64 commits ahead) |
| law | bundled submodule |
| python | 3.9 (columnar sandbox `venv_columnar_dev`) |
| host | DESY NAF (`naf-cms*.desy.de`), EL9 |
| analysis | `tt_semileptonic` (Run 3 2024 NanoAOD v15) |

---

## 1. `cf.PlotCutflow` fails: "Please project to 1D before calling plot"

### Status

Open upstream. Worked around locally (see below). Reproducible with a single MC
dataset and a single selection step.

### Symptom

`cf.PlotCutflow` runs its whole dependency tree successfully
(`SelectEvents` → `MergeSelectionStats` / `MergeSelectionMasks` →
`CreateCutflowHistograms`) and then fails in the final plotting step:

```
File ".../columnflow/tasks/cutflow.py", line 489, in run
    fig, _ = self.call_plot_func(
File ".../columnflow/tasks/framework/plotting.py", line 191, in call_plot_func
    return plot_func(**plot_kwargs)
File ".../columnflow/plotting/plot_functions_1d.py", line 414, in plot_cutflow
    fig, (ax,) = plot_all(plot_config, style_config, **kwargs)
File ".../columnflow/plotting/plot_all.py", line 402, in plot_all
    method_func(*args, **cfg.get("kwargs", {}))
File ".../columnflow/plotting/plot_all.py", line 199, in draw_stack
    h.plot(**defaults)
File ".../hist/stack.py", line 134, in plot
    return hist.plot.plot_stack(self, ax=ax, **kwargs)
File ".../hist/plot.py", line 783, in plot_stack
    raise NotImplementedError("Please project to 1D before calling plot")
NotImplementedError: Please project to 1D before calling plot
```

Command used:

```bash
law run cf.PlotCutflow --version test --calibrators default --selector default \
    --datasets tt_sl_powheg --processes tt_sl --categories incl
```

### Root cause

`cf.CreateCutflowHistograms` is a generic task: it histograms a **variable** split by
**selection step**, so it always builds the histogram with a variable axis. For the
plain event-count cutflow the variable is `event`, a deliberately single-binned
placeholder. The histogram it writes has five axes (verified by unpickling the output):

```
axes  : ['category', 'process', 'shift', 'step', 'event']
shape : (3, 1, 1, 3, 1)
```

`cf.PlotCutflow` wants a 1D bar chart (x = `step`), so `PlotCutflow.run()` must reduce
the four non-`step` axes. It reduces `category`, `process` and `shift`, but **not the
`event` (variable) axis**, so the histogram handed to the plot function is 2D
`(step, event)`.

This is a regression introduced by
**[columnflow#783](https://github.com/columnflow/columnflow/pull/783)**
("Improve leaf category handling in histograms", commit `33e7d67c`, 2026-03-02).
That PR factored category selection into the shared helper
`columnflow.hist_util.select_category_bins()` and, in `PlotCutflow.run()`, replaced

```python
# columnflow/tasks/cutflow.py — before #783
h = h[{"category": sum, self.variable: sum}]
```

with

```python
# columnflow/tasks/cutflow.py:483 — after #783
h = select_category_bins(h, category_inst, use_leaves=True, prefer_parents=True, reduce=True)
```

`select_category_bins()` only touches the `category` axis. The `self.variable: sum`
part was dropped and not moved anywhere, and the downstream `plot_cutflow` was not
updated to compensate. The analogous change in `PlotCutflowVariablesBase.run()`
(`cutflow.py:660`) is correct — that task legitimately keeps the variable axis.

### Why it surfaces as a somewhat confusing error

`columnflow.plotting.plot_functions_1d.plot_cutflow` assumes 1D input. Its helper
`columnflow.plotting.plot_util.hists_merge_cutflow_steps` is documented as *"Takes a
dict of 1D histogram objects with a single 'step' axis"* and, for two or more
processes, raises the clear

```
ValueError: cannot merge cutflow steps: histograms must be one-dimensional
```

(`plot_util.py:154`). But that check is guarded by `if len(hists) < 2: return`
(`plot_util.py:145`), so with a **single process** the validation is skipped, the 2D
histogram flows through `prepare_stack_plot_config()` and only blows up much later
inside `hist`'s `plot_stack` with the less obvious `NotImplementedError`.

`plot_cutflow` itself only removes the `shift` axis
(`remove_residual_axis(hists, "shift")`, `plot_functions_1d.py:356`); nothing removes
the variable axis.

### Suggested upstream fix

Restore the reduction in `PlotCutflow.run()`. After the `select_category_bins(...)`
call at `columnflow/tasks/cutflow.py:483`:

```python
# reduce every remaining non-step axis (the cutflow only plots event counts per step)
h = h[{ax: sum for ax in h.axes.name if ax != "step"}]
```

Optionally also harden `plot_cutflow` to reduce non-`step` axes at its entry point as
defense in depth. Note: it must be an unconditional `sum`, not
`remove_residual_axis(..., max_bins=1)`, because `--variable` can point at a
multi-bin variable and the event-count cutflow should still just sum it.

### Local workaround (this repo)

No submodule edit. A wrapper plot function that restores the pre-#783 behaviour:

- `tt_semileptonic/plotting/cutflow.py` — `plot_cutflow(hists, config_inst,
  category_inst, **kwargs)` sums every axis except `step`, then calls
  `columnflow.plotting.plot_functions_1d.plot_cutflow`.
- `tt_semileptonic/plotting/__init__` was renamed to `__init__.py` (it lacked the
  extension, so `tt_semileptonic.plotting` was not importable at all).
- `law.cfg`:

  ```ini
  [luigi_cf.PlotCutflow]
  plot_function: tt_semileptonic.plotting.cutflow.plot_cutflow
  ```

  law forwards `[luigi_<task family>]` sections to luigi as `[<task family>]`, which is
  where luigi reads per-task parameter defaults from; a plain `[cf.PlotCutflow]`
  section in `law.cfg` is **not** consulted by luigi's parameter resolver.

Remove all three once columnflow reduces the variable axis itself.

---

## 2. Tasks hang forever after finishing when input is read over XRootD

### Status

Environment / dependency issue (bundled XRootD client in the columnar sandbox).
Worked around by reading inputs from a local filesystem instead.

### Symptom

`cf.CalibrateEvents` / `cf.SelectEvents` (and anything that reads NanoAOD over a
`root://` redirector) complete their work — chunks processed, output parquet written,
luigi prints the success summary — and then the process **never exits**. The parent
`law` sits in `waitpid()` on the sandbox subprocess indefinitely; nothing is logged.

### Root cause

`gdb` backtrace of the stuck sandbox subprocess, main thread:

```
#2  XrdSys::IOEvents::Poller::SendCmd()
#3  XrdSys::IOEvents::Poller::Stop()
#4  XrdCl::PollerBuiltIn::Stop()
#5  XrdCl::PostMaster::Stop()
#6  XrdCl::DefaultEnv::Finalize()
#7  EnvInitializer::~EnvInitializer()        <-- libXrdCl static destructor
#8  __run_exit_handlers()
#9  exit()
#10 Py_Exit(sts=0)
#11 handle_system_exit()
```

Python exited cleanly with status 0; the C `atexit` handler of
`libXrdCl.so` (pulled in via the `gfal2` xrootd plugin,
`data/software/conda/lib/gfal2-plugins/../libXrdCl.so.6`) then deadlocks in
`XrdCl::DefaultEnv::Finalize()` → `Poller::Stop()`, blocked on a semaphore that is
never posted. The other threads are wedged `XrdCl` poller/socket threads in
`ShutdownEvents` / `ForceDisconnect` / `OnReadTimeout`, i.e. the redirector
connection went stale and the whole XrdCl teardown is stuck.

A task that **errors** exits before reaching the atexit handler, which is why failing
runs terminate normally and only successful runs hang.

`mttbar` (same framework, same site) does not hit this because its `law.cfg` lists a
POSIX dcache mount first in `[outputs] lfn_sources`, so it never opens an XRootD
connection for reading.

### Local workaround (this repo)

`law.cfg`:

```ini
[outputs]
lfn_sources: local_desy_dcache, wlcg_fs_infn_redirector, wlcg_fs_global_redirector

[local_desy_dcache]
base: /pnfs/desy.de/cms/tier2
rucio_report_access: False
```

Input NanoAOD is then read from `/pnfs/...` directly (no XRootD). If a required LFN is
not on the local Tier-2 disk, columnflow falls through to the XRootD redirectors and
the hang can return for that file.

### Notes for a framework fix

Options that would help, roughly in order of preference:
- have columnflow tasks `os._exit()` after a successful run instead of falling through
  to interpreter shutdown (skips all C `atexit` handlers, including XrdCl's);
- explicitly finalize / tear down the gfal2 / XRootD context before exit;
- pin / patch the bundled XRootD client to a version without the shutdown deadlock.
