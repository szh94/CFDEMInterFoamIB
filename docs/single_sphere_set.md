# Single-Sphere Tutorial

This document describes how to run the `tutorial/single_sphere` CFDEM case from
WSL. Run all commands from the tutorial directory unless stated otherwise:

```bash
cd /mnt/d/research/code/CFDEMInterFoamIB/tutorial/single_sphere
```

Before starting, load the OpenFOAM and CFDEM environment and verify that the
solver is available:

```bash
source ~/.bashrc
which solverInterIB20
```

## Step 1: Clean Previous Results

```bash
bash step1_allclean.sh
```

This removes previous logs, decomposed `processor*` directories, the generated
CFD mesh, and DEM post-processing output. This step is destructive: copy any
results that must be retained before running it.

## Step 2: Build and Initialize the CFD Mesh

```bash
bash step2_blockmeshsetfields.sh
```

The script restores `CFD/0/alpha.water` from `alpha.water.org`, runs
`blockMesh`, and initializes the phase field with `setFields`.

## Step 3: Run the Coupled CFD-DEM Simulation

Review the time controls and immersed-boundary coefficients before every run,
then start the parallel calculation:

```bash
bash step3_Allrun.sh
```

The script uses four MPI processes and runs `solverInterIB20` through the CFDEM
parallel-run helper. Logs are written under `single_sphere/log/`.

### Important time settings

The recommended settings in `CFD/system/controlDict` are:

```text
endTime         0.3;
deltaT          0.0002;
```

- `endTime` is the simulated physical end time. A value of `0.3` allows the
  particle and surrounding two-phase flow to develop for 0.3 seconds. Reducing
  it may stop the case before the behavior of interest is visible; increasing
  it increases runtime and storage and may expose later-time instabilities.
- `deltaT` is the fixed CFD time step because `adjustTimeStep` is set to `no`.
  It directly affects temporal resolution, interface transport, immersed-
  boundary forcing, and numerical stability. A larger value reduces runtime
  but can change the particle trajectory or make the calculation unstable. A
  smaller value normally improves time resolution but costs more computation.
- The DEM time step in `DEM/in.liggghts_run` is `0.00001`, and
  `couplingInterval` in `CFD/constant/couplingProperties` is `100`. Therefore,
  the CFD-DEM coupling period is `0.001` seconds. With `deltaT = 0.0002`, each
  coupling period contains exactly five CFD steps. Keep the CFD time step
  compatible with the coupling period when tuning it.
- With the current values, the solver performs 1,500 CFD time steps. Because
  `writeInterval` is `0.01`, fields are written every 50 CFD steps.

Do not use `CFD/system/controlDict.foam` as the active control dictionary. The
solver reads `CFD/system/controlDict`.

### Important immersed-boundary velocity coefficients

The recommended settings in `CFD/constant/couplingProperties` are:

```text
Coe_V_local             0.6;
Coe_V_global            0.85;
```

These coefficients directly scale the immersed-boundary particle-velocity
contribution applied to occupied CFD cells:

- `Coe_V_local` is selected when a particle overlaps a free-surface/interface
  region, detected by `0.02 < alpha.water < 0.98` in at least one particle
  cell. The current value `0.6` applies a weaker velocity correction near the
  interface.
- `Coe_V_global` is selected when the particle is not in that interface
  condition. The current value `0.85` applies the correction in the remainder
  of the domain.

Changing either coefficient changes the velocity field around the particle and
can consequently change hydrodynamic force, particle motion, interface shape,
and stability. The values `0.6` and `0.85` should be treated as part of the
validated setup, not as visualization-only parameters. Change one parameter at
a time, rerun from a clean initial state, and compare particle trajectory,
forces, phase distribution, and conservation behavior. Values outside the
expected range should only be used after verification against a reference case.

During the run, monitor the log for fatal errors, floating-point exceptions,
unbounded phase fractions, rapidly increasing residuals, and excessive
Courant/interface Courant numbers.

## Step 4: Reconstruct Parallel CFD Results

After the coupled run finishes, reconstruct the Eulerian CFD fields:

```bash
bash step4_reconstruct.sh
```

This executes `reconstructPar -noLagrangian` inside `CFD/`. The
`-noLagrangian` option intentionally skips CFDEM particle-position files that
standard OpenFOAM `reconstructPar` may not parse. Particle output remains under
`DEM/post/`.

## Step 5: Create a GIF

Place or export numbered PNG frames in `ani/` using this naming convention:

```text
ani1.0000.png
ani1.0001.png
ani1.0002.png
```

Then run:

```bash
bash step5_ani.sh
```

The script detects each frame-sequence prefix, prints the detected name and
frame count, and writes the GIF into the same directory. For the sequence above,
the output is `ani/ani1.gif`. Multiple prefixes are converted independently.

Pillow is required for GIF generation:

```bash
sudo apt-get install python3-pil
```

The `ani/` directory contains generated assets and is excluded by `.gitignore`.

## Complete Run Sequence

```bash
cd /mnt/d/research/code/CFDEMInterFoamIB/tutorial/single_sphere
source ~/.bashrc
bash step1_allclean.sh
bash step2_blockmeshsetfields.sh
bash step3_Allrun.sh
bash step4_reconstruct.sh
bash step5_ani.sh
```

Run Step 5 only after PNG animation frames have been exported to `ani/`.
