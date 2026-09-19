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

cd ./constant
rm -rf polyMesh

cd ../../DEM
rm -rf ./post
mkdir post
