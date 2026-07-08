#!/usr/bin/env bash
# rtr-survey-modprobe-block.sh
#
# Usage: rtr-survey-modprobe-block.sh <module1> [module2 ...]
#
# Output format (stdout):
#   Line 1:  ##RTR-SURVEY-START##
#   Line 2:  JSON array of per-module observations (blacklist state + loaded state)
#   Line 3:  JSON object containing uname -a output
#   Line 4:  ##RTR-SURVEY-END##
#
# The caller (rtr-vuln-runner.py) checks for the presence of ##RTR-SURVEY-END##.
# If it is absent, the script is assumed to have terminated prematurely on the
# target host and the host's data is marked incomplete/unknown.
#
# Intentionally collects facts only. Mitigation-status classification
# is performed by the caller, not here.
#
# Tested on: Ubuntu 20.04, 22.04, 24.04 / RHEL 8, 9

# Emit start sentinel before set -euo so it appears in stdout even if
# the script exits early due to a shell error.
printf '##RTR-SURVEY-START##\n'

set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo '{"error":"no modules specified"}' >&2
  exit 1
fi

modules=("$@")
sep=""
printf '['

for mod in "${modules[@]}"; do

  # Search all modprobe.d files for entries that block this module.
  # Matches:
  #   blacklist <module>
  #   install <module> /bin/false
  #   install <module> /dev/null
  block_entry=$(grep -rh \
    -e "^[[:space:]]*blacklist[[:space:]]\+${mod}[[:space:]]*$" \
    -e "^[[:space:]]*install[[:space:]]\+${mod}[[:space:]]\+/bin/false[[:space:]]*$" \
    -e "^[[:space:]]*install[[:space:]]\+${mod}[[:space:]]\+/dev/null[[:space:]]*$" \
    /etc/modprobe.d/ 2>/dev/null \
    | head -1 \
    | sed 's/^[[:space:]]*//' \
    || true)

  # Check whether the module is currently resident in the kernel.
  loaded_line=$(lsmod 2>/dev/null \
    | awk -v m="$mod" '$1 == m { print $0 }' \
    | head -1 \
    || true)

  # Escape any double-quotes in the block entry before embedding in JSON.
  block_entry_escaped=$(printf '%s' "$block_entry" | sed 's/\\/\\\\/g; s/"/\\"/g')

  if [[ -n "$block_entry" ]]; then
    block_json="\"${block_entry_escaped}\""
  else
    block_json="null"
  fi

  loaded_json=$( [[ -n "$loaded_line" ]] && echo 'true' || echo 'false' )

  printf '%s{"module":"%s","block_entry":%s,"loaded":%s}' \
    "$sep" "$mod" "$block_json" "$loaded_json"

  sep=","
done

printf ']\n'

# Emit uname -a as a second JSON object on its own line.
uname_a=$(uname -a 2>/dev/null || echo "unknown")
uname_escaped=$(printf '%s' "$uname_a" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"uname_a":"%s"}\n' "$uname_escaped"

printf '##RTR-SURVEY-END##\n'
