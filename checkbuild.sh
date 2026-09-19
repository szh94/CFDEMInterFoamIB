#!/bin/bash
#
# checkbuild.sh -- does the built library/executable postdate the sources?
#
# What runs at solve time is libinterIB20.so (built from subModels/), and the
# solver loads it dynamically, so the solver's own timestamp says nothing about
# whether a sub-model edit was compiled.  This walks those two chains --
# source -> object -> artifact -- and reports the link that is out of date.
#
#   ./checkbuild.sh
#
# Safe to run from any directory; it finds the project by its own path.
# Exit status: 0 all fresh, 1 something stale or missing.

set -u

root="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# wmake installs where CFDEM's bashrc says; fall back to its defaults so this
# still works in a shell that never sourced it.
user_dir="${CFDEM_PROJECT_USER_DIR:-$HOME/CFDEM/${LOGNAME:-${USER:-unknown}}-PUBLIC-5.x}"
opts="${WM_OPTIONS:-linux64GccDPInt32Opt}"
lib="${CFDEM_USER_LIB_DIR:-$user_dir/platforms/$opts/lib}/libinterIB20.so"
bin="${CFDEM_USER_APP_DIR:-$user_dir/platforms/$opts/bin}/solverInterIB20"

stale=0

show() {
    if [ -e "$1" ]; then
        printf '   %-56s %s\n' "${1#$root/}" "$(date -r "$1" '+%Y-%m-%d %H:%M:%S')"
    else
        printf '   %-56s %s\n' "${1#$root/}" '(missing)'
    fi
}

# Every input has to be older than the artifact it should have gone into.
newer_than() {
    local out=$1; shift
    if [ ! -e "$out" ]; then
        printf '   !! no such artifact: %s\n' "$out"
        stale=1
        return
    fi
    local out_t f
    out_t=$(stat -c %Y "$out")
    for f in "$@"; do
        if [ ! -e "$f" ]; then
            printf '   !! missing source: %s\n' "${f#$root/}"
            stale=1
        elif [ "$(stat -c %Y "$f")" -gt "$out_t" ]; then
            printf '   !! STALE: %s is newer than %s\n' "${f#$root/}" "${out#$root/}"
            stale=1
        fi
    done
}

sub_srcs=()
for f in "$root"/subModels/*/*.C; do
    case "$f" in */lnInclude/*) continue ;; esac
    sub_srcs+=("$f")
done

echo
echo "== subModels/  ->  libinterIB20.so"
show "$root/subModels/Make/$opts/options"   # wmake rewrites this on every run
for f in "${sub_srcs[@]}"; do
    rel="${f#$root/subModels/}"             # cloudInterIB/cloudInterIB2_0.C
    show "$f"
    # subModels objects mirror the source path; the solver's sit under Make/$opts
    show "$root/subModels/Make/subModels/${rel%.C}.o"
done
show "$lib"
newer_than "$lib" "${sub_srcs[@]}"

echo
echo "== src/  ->  solverInterIB20"
show "$root/src/solverInterIB2_0.C"
show "$root/Make/$opts/src/solverInterIB2_0.o"
show "$bin"
newer_than "$bin" "$root/src/solverInterIB2_0.C"

echo
if [ "$stale" -eq 0 ]; then
    echo "OK - every artifact postdates its sources."
else
    echo "STALE - rebuild from the project root; the subModels half is easy to miss."
fi
exit "$stale"
