#!/usr/bin/env bash
set -euo pipefail

actionlint=${1:?Path to actionlint is required}
zizmor=${2:?Path to zizmor is required}

# Use the same tracked workflow paths for both scanners, including future .yaml files.
workflow_list=$(mktemp)
trap 'rm -f -- "$workflow_list"' EXIT
git ls-files -z -- ':(top,glob).github/workflows/*.yml' ':(top,glob).github/workflows/*.yaml' > "$workflow_list"
mapfile -d '' -t workflows < "$workflow_list"
if (( ${#workflows[@]} == 0 )); then
  echo "No tracked GitHub Actions workflows to scan" >&2
  exit 1
fi
for workflow in "${workflows[@]}"; do
  if [[ ! -f "$workflow" || -L "$workflow" ]]; then
    printf 'Expected a regular workflow file: %q\n' "$workflow" >&2
    exit 1
  fi
done

result=0
"$actionlint" -shellcheck "" -pyflakes "" "${workflows[@]}" || result=1
"$zizmor" --offline --strict-collection --no-ignores --persona regular "${workflows[@]}" || result=1
exit "$result"
