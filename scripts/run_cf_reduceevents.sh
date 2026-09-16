law run cf.ReduceEvents --dataset tt_sl_powheg --version test --calibrators default --selector default --reducer cf_default

# --reducer must be given explicitly: cfg.x.default_reducer = "default" in
# defaults_and_groups_helper.py points at a reducer name that doesn't exist (only
# "cf_default", from columnflow.reduction.default, and "example", from
# tt_semileptonic.reduction.example, are registered in law.cfg's reduction_modules) --
# same class of mismatch as default_calibrator = "skip_jecunc" (see AGENTS.md).

# This runs cf.ReduceEvents on multiple datasets, same pattern as cf.SelectEventsWrapper
# law run cf.ReduceEventsWrapper --datasets mc --branch 0 \
#     --version test --calibrators default --selector default --reducer cf_default --workers 4
