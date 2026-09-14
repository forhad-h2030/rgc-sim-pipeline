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

`$WORKROOT` inside the script points at the pre-built shared artifacts
(`/project/ptgroup/Forhad/MC-HallB`: coatjava, GEMC sandbox, generators,
Python venv) -- those must already exist; see CLAUDE.md in the main
RGC-ANA repo for how they were built.

## Submit

```bash
sbatch rivanna_pipeline.slurm                    # sidis, 1000 events
PHYSICS=jpsi sbatch rivanna_pipeline.slurm
PHYSICS=dvcs NEVENTS=200000 sbatch rivanna_pipeline.slurm   # genepi: NEVENTS = raw trials, not kept events
PHYSICS=dvcs_dvcsgen NEVENTS=1000 sbatch rivanna_pipeline.slurm  # dvcsgen: NEVENTS = kept events
sbatch --array=0-9 rivanna_pipeline.slurm        # 10 jobs, unique seeds
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

## New physics channel

Add `configs/<name>.conf` (define `GCARD_DEFAULT` + `run_generator()`,
leave LUND at `$jobdir/eventfiles/gen.dat`) and `configs/<name>.params`.
Nothing else changes -- stages 2-4 only care about the LUND file format.

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
