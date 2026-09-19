#!/bin/bash

set -e

# Resolve the case path so the script can be launched from any directory.
casePath="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
projectPath="$(readlink -f "$casePath/../..")"

# Curves are drawn from DEM/post into <case>/results/.
python3 "$projectPath/pyScript/plot_dem_curve.py" "$casePath"
