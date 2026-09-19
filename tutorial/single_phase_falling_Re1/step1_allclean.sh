#!/bin/bash
# consolidated case logs (single_sphere/log)
rm -rf ./log
mkdir -p ./log
# old pre-reorg location of the solver log (if any)
rm -f ./log_CFDEM_IB

cd ./CFD
rm -f ani.*
rm -f log.liggghts   # auto-created stub by embedded LAMMPS in CFD cwd
rm -rf processor*
# reconstructed time directories -- everything but the initial 0, which holds
# the field step2 writes
for time in [0-9]*; do
    [ "$time" = 0 ] && continue
    case "$time" in *[!0-9.]*) continue;; esac
    rm -rf "$time"
done

cd ./constant
rm -rf polyMesh

cd ../../DEM
rm -rf ./post
mkdir post
