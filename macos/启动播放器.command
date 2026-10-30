#!/bin/zsh
set -eu
project=${0:A:h:h}
cd "$project"
"$project/.venv/bin/python" -m macos.launch
