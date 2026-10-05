#!/usr/bin/env bash
# Весь код проекта одним файлом для ассистента: output/code_dump.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p output
{
  echo "### git log"; git log --oneline -n 40
  echo; echo "### git status"; git status --short
  echo; echo "### файлы"; git ls-files --cached --others --exclude-standard | sort
  git ls-files -z --cached --others --exclude-standard -- \
      '*.py' '*.toml' '*.ini' '*.cfg' '*.md' '*.sql' '*.mako' '*.sh' \
      '*.html' '*.jinja' '*.j2' '*.js' '*.css' '*.yml' '*.yaml' \
      '*.service' '*.timer' '*.conf' '.env.example' \
    | sort -z \
    | xargs -0 -I{} sh -c 'printf "\n=== %s\n" "$1"; cat "$1"' _ {}
} > output/code_dump.txt
wc -l -c output/code_dump.txt
