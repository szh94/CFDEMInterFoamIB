#!/bin/bash

set -e

# Resolve the case path so the script can be launched from any directory.
casePath="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
projectPath="$(readlink -f "$casePath/../..")"

python3 "$projectPath/pyScript/png_to_gif.py" "$casePath/ani"
