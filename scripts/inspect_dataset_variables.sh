DATASET="${1}"

# Get redirector base
CONFIG="$(cat "$TT_SEMILEPTONIC_BASE/law.cfg")"
CONFIG="${CONFIG##*\[wlcg_fs_global_redirector\]}"
CONFIG="${CONFIG%%\[}"
REDIRECTOR_BASE="$(grep "base:" <<< "$CONFIG")"
REDIRECTOR_BASE="${REDIRECTOR_BASE##*base: }"
REDIRECTOR_BASE="${REDIRECTOR_BASE%/*}/"

# get dataset paths
readarray -t DATASET_JSONS < <(law run cf.GetDatasetLFNs --dataset "$DATASET" --print-output 0 | grep "file://" | sed "s#file://##g")

# get first rootfile from DATASET_JSONS
ROOTFILE="$(cat "${DATASET_JSONS[0]}")"
ROOTFILE="${ROOTFILE#*\"}"
ROOTFILE="${ROOTFILE%%\"*}"

echo "'objects[0].to_list()' will output all available variables"
cf_inspect "${REDIRECTOR_BASE}${ROOTFILE}"