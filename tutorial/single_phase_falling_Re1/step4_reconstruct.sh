#!/bin/bash

# Resolve the case path so the script can be launched from any directory.
casePath="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

cd "$casePath/CFD" || exit 1
# Reconstruct Eulerian CFD fields only. CFDEM particle positions are handled by
# LIGGGHTS and may not use a format that reconstructPar can read reliably.
reconstructPar -noLagrangian
