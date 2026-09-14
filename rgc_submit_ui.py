"""
Desktop submission form for rgc-sim-pipeline, styled after the CLAS12
OSG portal's job form. Runs either:
  - locally on a Mac, ssh-ing into Rivanna to submit (needs ~/.ssh/id_rsa
    already set up), or
  - directly on Rivanna itself (e.g. via ssh -X for X11-forwarded
    display), calling sbatch with no ssh hop at all.
Detected automatically via whether `sbatch` exists on this machine.

Run: python3 rgc_submit_ui.py
"""
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

SSH_HOST = "dgy5cd@login.hpc.virginia.edu"
SSH_KEY = "~/.ssh/id_rsa"
REMOTE_DIR = "/project/ptgroup/Forhad/rgc-sim-pipeline"
ON_RIVANNA = shutil.which("sbatch") is not None
POLL_SECONDS = 15

GENERATORS = {
    "sidis": "clasdis -- SIDIS",
    "jpsi": "JPsiGen -- J/psi photoproduction, e+e- decay",
    "dvcs": "genepi -- proton-DVCS (BH+DVCS), NEVENTS = raw trials",
    "dvcs_dvcsgen": "dvcsgen -- proton-DVCS, NEVENTS = kept events",
}

# genepi's keep/reject acceptance is ~0.07% for its default kinematic
# range, so 1000 raw trials (a fine default for the others) yields 0
# kept events almost every time -- confirmed by a real failed job.
DEFAULT_NEVENTS = {
    "sidis": "1000",
    "jpsi": "1000",
    "dvcs": "200000",
    "dvcs_dvcsgen": "1000",
}

GCARDS = ["rgc_summer2022.gcard", "rgc_fall2022.gcard", "rgc_spring2023.gcard"]

STATE_COLOR = {
    "SUBMITTING": "#dddddd",
    "PENDING": "#f1c40f",        # yellow
    "CONFIGURING": "#3498db",    # blue
    "RUNNING": "#3498db",        # blue
    "COMPLETED": "#2ecc71",      # green
    "CANCELLED": "#e74c3c",      # red
    "FAILED": "#e74c3c",         # red
    "TIMEOUT": "#e74c3c",        # red
    "OUT_OF_MEMORY": "#e74c3c",  # red
    "NODE_FAIL": "#e74c3c",      # red
    "SUBMIT_FAILED": "#e74c3c",  # red
    "UNKNOWN": "#dddddd",
}
# Worst-first: a single failed/cancelled task always wins the display,
# even if other tasks in the same array job succeeded.
STATE_PRIORITY = ["CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "SUBMIT_FAILED",
                   "PENDING", "CONFIGURING", "SUBMITTING", "RUNNING", "COMPLETED"]


def _aggregate_state(states):
    for s in STATE_PRIORITY:
        if s in states:
            return s
    return "UNKNOWN"


class SubmitForm(tk.Tk):
    def __init__(self):
        super().__init__()
        mode = "local sbatch" if ON_RIVANNA else f"ssh -> {SSH_HOST}"
        self.title(f"rgc-sim-pipeline submission [{mode}]")
        self.geometry("640x640")
        self.columnconfigure(1, weight=1)
        self._row_i = 0
        self.jobs = {}  # job_id -> {"row": tree item id, "n_tasks": int, "physics": str}
        self._build()

    def _next_row(self):
        r = self._row_i
        self._row_i += 1
        return r

    def _field(self, label_text, widget):
        r = self._next_row()
        ttk.Label(self, text=label_text).grid(row=r, column=0, sticky="w", padx=12, pady=6)
        widget.grid(row=r, column=1, sticky="ew", padx=(0, 12), pady=6)
        return r

    def _note(self, text):
        r = self._next_row()
        ttk.Label(self, text=text, foreground="gray").grid(
            row=r, column=1, sticky="w", padx=(0, 12), pady=(0, 4))

    def _build(self):
        # Configuration (gcard)
        self.gcard_var = tk.StringVar(value=GCARDS[0])
        gcard_box = ttk.Combobox(self, textvariable=self.gcard_var,
                                  values=GCARDS, state="readonly")
        self._field("Configuration", gcard_box)

        # Magnetic Fields -- NOT wired into the pipeline yet
        self._field("Magnetic Fields", ttk.Label(
            self, text="tor-1.00 / sol-1.00", relief="sunken", padding=(6, 3)))
        self._note("not yet supported -- fixed by the gcard")

        # Generator
        self.gen_var = tk.StringVar(value="sidis")
        gen_box = ttk.Combobox(self, textvariable=self.gen_var,
                                values=list(GENERATORS.keys()), state="readonly")
        gen_box.bind("<<ComboboxSelected>>", self._update_gen_desc)
        self._field("Generator", gen_box)

        r = self._next_row()
        self.gen_desc = ttk.Label(self, text=GENERATORS["sidis"], foreground="gray")
        self.gen_desc.grid(row=r, column=1, sticky="w", padx=(0, 12), pady=(0, 4))

        self._note("physics settings: edit configs/<gen>.params on Rivanna")

        # Run label -- free-text note saved into data/.../run_info.txt
        # and folded into the SLURM job name, so runs are identifiable later.
        self.label_var = tk.StringVar(value="")
        self._field("Run Label", ttk.Entry(self, textvariable=self.label_var))
        self._note("optional note, saved with the run (e.g. \"vertex test\")")

        # Number of events per job
        self.nevents_var = tk.StringVar(value="1000")
        nevents_entry = ttk.Entry(self, textvariable=self.nevents_var)
        nevents_entry.bind("<KeyRelease>", self._update_total)
        self._field("Events / Job", nevents_entry)

        # Number of jobs
        self.njobs_var = tk.StringVar(value="1")
        njobs_entry = ttk.Entry(self, textvariable=self.njobs_var)
        njobs_entry.bind("<KeyRelease>", self._update_total)
        self._field("Number of Jobs", njobs_entry)

        # Total events (computed, read-only)
        self.total_var = tk.StringVar(value="1000")
        total_entry = ttk.Entry(self, textvariable=self.total_var, state="readonly")
        self._field("Total Events", total_entry)

        # Background Merging -- NOT wired into the pipeline yet
        self._field("Background Merging", ttk.Label(
            self, text="none", relief="sunken", padding=(6, 3)))
        self._note("not yet supported by the pipeline")

        r = self._next_row()
        ttk.Separator(self).grid(row=r, column=0, columnspan=2, sticky="ew", padx=12, pady=10)

        r = self._next_row()
        btn_row = ttk.Frame(self)
        btn_row.grid(row=r, column=0, columnspan=2, pady=6)
        self.submit_btn = ttk.Button(btn_row, text="Submit", command=self._submit)
        self.submit_btn.pack(side="left", padx=6)
        ttk.Button(btn_row, text="Clear History", command=self._clear_history).pack(side="left", padx=6)

        # Job history table -- one row per submitted job, live status color.
        r = self._next_row()
        columns = ("physics", "label", "status", "output")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings", height=12)
        self.tree.heading("#0", text="Job ID")
        self.tree.heading("physics", text="Generator")
        self.tree.heading("label", text="Label")
        self.tree.heading("status", text="Status")
        self.tree.heading("output", text="Output")
        self.tree.column("#0", width=80, anchor="w")
        self.tree.column("physics", width=90, anchor="w")
        self.tree.column("label", width=100, anchor="w")
        self.tree.column("status", width=110, anchor="w")
        self.tree.column("output", width=180, anchor="w")
        for state, color in STATE_COLOR.items():
            self.tree.tag_configure(state, background=color)
        self.tree.grid(row=r, column=0, columnspan=2, sticky="nsew", padx=12, pady=8)
        self.rowconfigure(r, weight=1)

    def _update_gen_desc(self, _event=None):
        gen = self.gen_var.get()
        self.gen_desc.config(text=GENERATORS[gen])
        self.nevents_var.set(DEFAULT_NEVENTS[gen])
        self._update_total()

    def _update_total(self, _event=None):
        try:
            n = int(self.nevents_var.get()) * int(self.njobs_var.get())
            self.total_var.set(str(n))
        except ValueError:
            self.total_var.set("?")

    def _clear_history(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.jobs.clear()

    def _set_row(self, job_id, physics=None, label=None, status=None, output=None):
        """Update a job's row if it still exists (may have been cleared)."""
        info = self.jobs.get(job_id)
        if not info:
            return
        row = info["row"]
        if not self.tree.exists(row):
            return
        cur = self.tree.item(row, "values")
        new_physics = physics if physics is not None else cur[0]
        new_label = label if label is not None else cur[1]
        new_status = status if status is not None else cur[2]
        new_output = output if output is not None else cur[3]
        self.tree.item(row, values=(new_physics, new_label, new_status, new_output),
                        tags=(new_status,))

    def _run(self, cmd_str, timeout=30):
        """Run cmd_str either locally (on Rivanna) or over ssh, return CompletedProcess."""
        if ON_RIVANNA:
            cmd = ["bash", "-c", cmd_str]
        else:
            cmd = ["ssh", "-o", "BatchMode=yes", "-i", SSH_KEY, SSH_HOST, cmd_str]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _submit(self):
        try:
            nevents = int(self.nevents_var.get())
            njobs = int(self.njobs_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Events/Job and Number of Jobs must be integers.")
            return

        gcard = self.gcard_var.get()
        physics = self.gen_var.get()
        label = self.label_var.get().strip()
        safe_label = re.sub(r"[^A-Za-z0-9_-]+", "-", label)[:30]
        job_name = f"rgc-{physics}" + (f"-{safe_label}" if safe_label else "")

        array_flag = f"--array=0-{njobs - 1} " if njobs > 1 else ""
        sbatch_cmd = (
            f'cd {REMOTE_DIR} && PHYSICS={physics} NEVENTS={nevents} GCARD={gcard} '
            f'RUN_LABEL="{label}" sbatch --job-name="{job_name}" {array_flag}rivanna_pipeline.slurm'
        )

        self.submit_btn.config(state="disabled")
        row = self.tree.insert("", "end", text="...", values=(physics, label, "SUBMITTING", "-"),
                                tags=("SUBMITTING",))

        try:
            result = self._run(sbatch_cmd)
        except Exception as e:
            self.tree.item(row, values=(physics, label, "SUBMIT_FAILED", str(e)[:40]),
                            tags=("SUBMIT_FAILED",))
            self.submit_btn.config(state="normal")
            return
        finally:
            self.submit_btn.config(state="normal")

        out = result.stdout.strip()
        if result.returncode != 0:
            self.tree.item(row, values=(physics, label, "SUBMIT_FAILED", result.stderr.strip()[:40]),
                            tags=("SUBMIT_FAILED",))
            return

        m = re.search(r"Submitted batch job (\d+)", out)
        if not m:
            self.tree.item(row, values=(physics, label, "SUBMIT_FAILED", "no job ID in sbatch output"),
                            tags=("SUBMIT_FAILED",))
            return

        job_id = m.group(1)
        self.tree.item(row, text=job_id, values=(physics, label, "PENDING", "-"), tags=("PENDING",))
        self.jobs[job_id] = {"row": row, "n_tasks": njobs, "physics": physics}
        threading.Thread(target=self._poll, args=(job_id, physics, njobs), daemon=True).start()

    def _poll(self, job_id, physics, n_tasks):
        while True:
            time.sleep(POLL_SECONDS)
            try:
                r = self._run(f"squeue -j {job_id} -h -o %T", timeout=15)
            except Exception:
                continue
            states = [s for s in r.stdout.strip().splitlines() if s]
            if not states:
                break
            agg = _aggregate_state(states)
            self.after(0, self._set_row, job_id, None, None, agg)

        final_states = []
        try:
            r = self._run(
                f"sacct -j {job_id} --format=JobID,State,ExitCode --noheader | grep -v '\\.'",
                timeout=15,
            )
            for line in r.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    final_states.append(parts[1])
        except Exception:
            pass

        agg = _aggregate_state(final_states) if final_states else "UNKNOWN"
        output_paths = "; ".join(f"data/{physics}_*_{job_id}_{t}/" for t in range(n_tasks))
        self.after(0, self._set_row, job_id, None, None, agg, output_paths)


if __name__ == "__main__":
    SubmitForm().mainloop()
