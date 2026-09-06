law run cf.SelectEvents --dataset tt_sl_powheg --version test --calibrators default --selector default

# equivalent for mttbar is
# law run cf.SelectEvents \
#     --dataset tt_sl_powheg \
#     --version test \
#     --config run3_mtt_2024_nano_v15_limited_new \
#     --calibrators skip_jecunc \
#     --selector default \
#     --branch 0