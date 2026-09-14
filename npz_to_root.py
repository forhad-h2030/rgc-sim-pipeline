"""
Convert a hipo2npz .npz file to a ROOT file with proper jagged
(per-event, variable-length) branches.

IMPORTANT: hipo2npz silently DROPS an event entirely from a bank's
arrays when that bank has zero rows for that event (e.g. REC::Particle
for an event where nothing was reconstructed) -- it does not write a
placeholder empty row, and it does not expose which specific events
were dropped. So when two banks end up with different total event
counts in the same file (seen in practice: MC::Lund can have MORE
events than REC::Particle/REC::Event, since GEMC writes truth for every
simulated event but the reconstruction skips events with nothing to
report), there is no way to realign them index-for-index after the
fact.

To avoid crashing (uproot requires every branch in one TTree to have
the same number of entries) or silently corrupting alignment, banks are
grouped by their actual event count and written as SEPARATE trees, one
per distinct count. When all banks share the same count (the common
case), this produces a single "tree" exactly as before. When they
don't, you get multiple trees (e.g. "tree" and "tree_162") and should
not assume entry i in one lines up with entry i in the other.
"""
import sys

import awkward as ak
import numpy as np
import uproot

npz_path, root_path = sys.argv[1], sys.argv[2]
d = np.load(npz_path)

banks = set(k.split("__rows_per_event")[0] for k in d.files if k.endswith("__rows_per_event"))

# Group banks by their actual event count.
groups = {}  # nevents -> {branch_name: jagged_array}
for bank in banks:
    counts = d[f"{bank}__rows_per_event"]
    nevents = len(counts)
    groups.setdefault(nevents, {})
    for key in d.files:
        prefix = f"{bank}__"
        if not key.startswith(prefix):
            continue
        field = key[len(prefix):]
        if field in ("rows_per_event", "offsets"):
            continue
        branch_name = f"{bank}_{field}"
        groups[nevents][branch_name] = ak.unflatten(d[key], counts)

if len(groups) > 1:
    print(f"WARNING: banks have mismatched event counts {sorted(groups.keys())} "
          f"-- writing as separate trees, entries do NOT align across trees")

with uproot.recreate(root_path) as f:
    sorted_counts = sorted(groups.keys(), reverse=True)
    for i, nevents in enumerate(sorted_counts):
        tree_name = "tree" if i == 0 else f"tree_{nevents}"
        f[tree_name] = groups[nevents]
        print(f"  {tree_name}: {len(groups[nevents])} branches, {nevents} events")

print(f"Wrote {root_path}")
