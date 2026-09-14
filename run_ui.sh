#!/bin/bash
# Launches rgc_submit_ui.py. On Rivanna, loads the modules tkinter
# needs first (the Mac's own python3 already has tkinter built in, so
# `module` won't exist there and this is skipped).
if command -v module >/dev/null 2>&1; then
    module load gcc/11.4.0 openmpi/4.1.4 python/3.11.4
fi
exec python3 "$(dirname "$0")/rgc_submit_ui.py"
