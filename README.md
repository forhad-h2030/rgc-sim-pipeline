# rgc-sim-pipeline

Generate -> simulate (GEMC) -> reconstruct (coatjava) -> ROOT, one SLURM
job per submission, on Rivanna.

## Layout

```
rivanna_pipeline.slurm   the submission script
configs/<channel>.conf   generator wiring (bash function)
configs/<channel>.params physics settings, edit these, not .conf
data/<channel>_<date>_<jobid>_<task>/   per-job output
logs/                    SLURM stdout/stderr
```

`$WORKROOT` inside the script points at the pre-built shared software
(`/project/ptgroup/Forhad/MC-HallB`: coatjava, GEMC sandbox, generators,
Python venv). Those must already exist; they are built separately, not
part of this repo.

## GUI (optional)

```bash
./run_ui.sh
```
Form for Configuration/Generator/Events/Jobs/Run Label, submits and
polls job status. Works two ways: run locally on a Mac (ssh's into
Rivanna to submit) or directly on Rivanna via `ssh -X` (needs XQuartz
on the Mac side, calls `sbatch` directly, no ssh hop). Title bar shows
which mode it's in.

## Submit

Default: sidis, 1000 events.
```bash
sbatch rivanna_pipeline.slurm
```

J/psi channel (JPsiGen).
```bash
PHYSICS=jpsi sbatch rivanna_pipeline.slurm
```

DVCS via genepi. NEVENTS = raw trials, not kept events.
```bash
PHYSICS=dvcs NEVENTS=200000 sbatch rivanna_pipeline.slurm
```

DVCS via dvcsgen. NEVENTS = kept events (1:1, unlike genepi).
```bash
PHYSICS=dvcs_dvcsgen NEVENTS=1000 sbatch rivanna_pipeline.slurm
```

Array job: 10 jobs, unique seeds and data dirs.
```bash
sbatch --array=0-9 rivanna_pipeline.slurm
```

Override the gcard (detector config).
```bash
GCARD=rgc_fall2022.gcard sbatch rivanna_pipeline.slurm
```

Channels: `sidis` (clasdis), `jpsi` (JPsiGen), `dvcs` (genepi), `dvcs_dvcsgen` (dvcsgen).

## Change physics settings

Edit `configs/<channel>.params` (plain `KEY=value`). Don't edit `.conf`
unless changing how the generator is invoked.

## Check a job

```bash
squeue -u $USER
cat logs/slurm-<jobid>_*.out
ls data/<channel>_<date>_<jobid>_<task>/
```

Final output per job: `data/.../out_recon.root`.

## Customize the reconstructed HIPO / ROOT content

Both are controlled directly in `rivanna_pipeline.slurm`, not via env vars:

- **Reconstructed HIPO content** (Stage 3): the `recon-util` line's `-c`
  flag picks which services run (`0` none, `1` default, `2` all). Add
  `-y <yaml>` to point at a specific `clas12-config` yaml for a given
  run period/variation instead of the default calibration.
- **ROOT bank selection** (Stage 4): the `hipo2npz` line. No bank list
  after the input/output paths converts every bank (current default);
  add a comma-separated list (e.g. `REC::Particle,REC::Event,MC::Lund`)
  to convert only those. A commented-out example with that narrower
  list is left right below the active line.

## New physics channel

Add `configs/<name>.conf` (define `GCARD_DEFAULT` + `run_generator()`,
leave LUND at `$jobdir/eventfiles/gen.dat`) and `configs/<name>.params`.
Nothing else changes: stages 2-4 only care about the LUND file format.

## Sources (what each stage actually runs)

| Stage | Tool | Repo |
|---|---|---|
| 1 (sidis) | clasdis | github.com/JeffersonLab/clasdis |
| 1 (jpsi) | JPsiGen | github.com/JeffersonLab/JPsiGen |
| 1 (dvcs) | genepi | github.com/N-Plx/genepi |
| 1 (dvcs_dvcsgen) | dvcsgen | github.com/JeffersonLab/dvcsgen |
| 2 | GEMC | hub.docker.com jeffersonlab/gemc, via Apptainer sandbox |
| 2 | gcards | github.com/JeffersonLab/clas12-config |
| 3 | coatjava | github.com/JeffersonLab/coatjava |
| 4 | hipo2npz | bundled in coatjava (PR #1365) |
| 4 | uproot/awkward | PyPI, in `$WORKROOT/venv` |
