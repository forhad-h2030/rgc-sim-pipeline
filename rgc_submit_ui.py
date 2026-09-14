"""
Desktop submission form for rgc-sim-pipeline on Rivanna, styled after the
CLAS12 OSG portal's job form. Submits via ssh + sbatch using the same
~/.ssh/id_rsa key used throughout this project.

Run: python3 rgc_submit_ui.py
"""
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

SSH_HOST = "dgy5cd@login.hpc.virginia.edu"
SSH_KEY = "~/.ssh/id_rsa"
REMOTE_DIR = "/project/ptgroup/Forhad/rgc-sim-pipeline"

GENERATORS = {
    "sidis": "clasdis -- SIDIS",
    "jpsi": "JPsiGen -- J/psi photoproduction, e+e- decay",
    "dvcs": "genepi -- proton-DVCS (BH+DVCS), NEVENTS = raw trials",
    "dvcs_dvcsgen": "dvcsgen -- proton-DVCS, NEVENTS = kept events",
}

GCARDS = ["rgc_summer2022.gcard", "rgc_fall2022.gcard", "rgc_spring2023.gcard"]


class SubmitForm(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("rgc-sim-pipeline submission")
        self.geometry("520x520")
        self._build()

    def _row(self, label_text, widget):
        row = ttk.Frame(self)
        row.pack(fill="x", padx=12, pady=6)
        ttk.Label(row, text=label_text, width=20).pack(side="left")
        widget.pack(side="left", fill="x", expand=True)
        return row

    def _build(self):
        # Configuration (gcard)
        self.gcard_var = tk.StringVar(value=GCARDS[0])
        gcard_box = ttk.Combobox(self, textvariable=self.gcard_var,
                                  values=GCARDS, state="readonly")
        self._row("Configuration", gcard_box)

        # Magnetic Fields -- NOT wired into the pipeline yet
        mag_var = tk.StringVar(value="tor-1.00_sol-1.00 (fixed in gcard)")
        mag_box = ttk.Combobox(self, textvariable=mag_var,
                                values=[mag_var.get()], state="disabled")
        self._row("Magnetic Fields", mag_box)
        ttk.Label(self, text="not yet supported -- fixed by the gcard",
                  foreground="gray").pack(anchor="w", padx=140)

        # Generator
        self.gen_var = tk.StringVar(value="sidis")
        gen_box = ttk.Combobox(self, textvariable=self.gen_var,
                                values=list(GENERATORS.keys()), state="readonly")
        gen_box.bind("<<ComboboxSelected>>", self._update_gen_desc)
        self._row("Generator", gen_box)

        self.gen_desc = ttk.Label(self, text=GENERATORS["sidis"], foreground="gray")
        self.gen_desc.pack(anchor="w", padx=140)

        ttk.Label(self, text="Physics settings: edit configs/<gen>.params on Rivanna",
                  foreground="gray").pack(anchor="w", padx=12, pady=(4, 0))

        # Number of events per job
        self.nevents_var = tk.StringVar(value="1000")
        nevents_entry = ttk.Entry(self, textvariable=self.nevents_var)
        nevents_entry.bind("<KeyRelease>", self._update_total)
        self._row("Events / Job", nevents_entry)

        # Number of jobs
        self.njobs_var = tk.StringVar(value="1")
        njobs_entry = ttk.Entry(self, textvariable=self.njobs_var)
        njobs_entry.bind("<KeyRelease>", self._update_total)
        self._row("Number of Jobs", njobs_entry)

        # Total events (computed, read-only)
        self.total_var = tk.StringVar(value="1000")
        total_entry = ttk.Entry(self, textvariable=self.total_var, state="readonly")
        self._row("Total Events", total_entry)

        # Background Merging -- NOT wired into the pipeline yet
        bg_var = tk.StringVar(value="none")
        bg_box = ttk.Combobox(self, textvariable=bg_var, values=["none"], state="disabled")
        self._row("Background Merging", bg_box)
        ttk.Label(self, text="not yet supported by the pipeline",
                  foreground="gray").pack(anchor="w", padx=140)

        ttk.Separator(self).pack(fill="x", padx=12, pady=10)

        submit = ttk.Button(self, text="Submit", command=self._submit)
        submit.pack(pady=6)

        self.output = tk.Text(self, height=10, wrap="word")
        self.output.pack(fill="both", expand=True, padx=12, pady=8)

    def _update_gen_desc(self, _event=None):
        self.gen_desc.config(text=GENERATORS[self.gen_var.get()])

    def _update_total(self, _event=None):
        try:
            n = int(self.nevents_var.get()) * int(self.njobs_var.get())
            self.total_var.set(str(n))
        except ValueError:
            self.total_var.set("?")

    def _log(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _submit(self):
        try:
            nevents = int(self.nevents_var.get())
            njobs = int(self.njobs_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Events/Job and Number of Jobs must be integers.")
            return

        gcard = self.gcard_var.get()
        physics = self.gen_var.get()

        array_flag = f"--array=0-{njobs - 1} " if njobs > 1 else ""
        remote_cmd = (
            f"cd {REMOTE_DIR} && "
            f"PHYSICS={physics} NEVENTS={nevents} GCARD={gcard} "
            f"sbatch {array_flag}rivanna_pipeline.slurm"
        )
        ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-i", SSH_KEY, SSH_HOST, remote_cmd]

        self._log(f"$ {remote_cmd}")
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
            self._log(result.stdout.strip())
            if result.returncode != 0:
                self._log(f"[error, exit {result.returncode}] {result.stderr.strip()}")
        except Exception as e:
            self._log(f"[submission failed] {e}")


if __name__ == "__main__":
    SubmitForm().mainloop()
