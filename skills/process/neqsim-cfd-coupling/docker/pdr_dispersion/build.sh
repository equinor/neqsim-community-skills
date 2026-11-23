#!/bin/sh
# Build r5PDRFoam: PDRFoam from OpenFOAM v2512 with an fvOptions source in the mixture-fraction equation (ftEqn.H), so a leak can be
# injected as a mass + fuel + momentum source (cell zone) and a steady/transient dispersion cloud can be computed in the SAME PDR
# geometry and mesh that the explosion run uses. Run inside the image:
#   docker run --rm -v "$PWD:/work" opencfd/openfoam-default:latest bash -lc \
#       "cd /work/docker/pdr_dispersion && sh build.sh /work/bin"
set -e
OUT=${1:-/work/bin}
mkdir -p "$OUT"
SRC=$WM_PROJECT_DIR/applications/solvers/combustion/PDRFoam
TMP=${TMPDIR:-/tmp}/r5PDRFoam
rm -rf "$TMP" && cp -r "$SRC" "$TMP"
cp "$(dirname "$0")/ftEqn.H" "$TMP/ftEqn.H"
sed -i 's#EXE = \$(FOAM_APPBIN)/PDRFoam#EXE = $(FOAM_USER_APPBIN)/r5PDRFoam#' "$TMP/Make/files"
export FOAM_USER_APPBIN="$OUT"
cd "$TMP" && wmake > "$OUT/wmake.log" 2>&1
ls -l "$OUT/r5PDRFoam"
