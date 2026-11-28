set -eu
cd /root/autodl-tmp/dog-and-arm-mm03
work=/root/autodl-tmp/mm03-20261126/performance/20261128-host-rows
export PYTHONPATH=.:scripts CUBLAS_WORKSPACE_CONFIG=:4096:8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
for phase in original compact; do
  if ! test -s "$work/$phase.json"; then
    nice -n 7 .conda/envs/arm-and-dog/bin/python -u "$work/row_check.py" "$phase"
  fi
done
