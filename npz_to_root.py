"""
Convert a hipo2npz .npz file to a ROOT file with jagged branches.
Banks with mismatched event counts (hipo2npz can drop events with zero
rows) go into separate trees ("tree", "tree_<n>") instead of crashing.
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
