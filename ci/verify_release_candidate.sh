#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORK="$ROOT/.build/ci"
mkdir -p "$WORK/home" "$WORK/tmp" "$WORK/cache" "$WORK/wheel-a" "$WORK/wheel-b" "$WORK/sdist" "$WORK/sdist-b" "$WORK/sdist-wheel" "$WORK/extracted-sdist"
chmod 700 "$WORK"
export HOME="$WORK/home" TMPDIR="$WORK/tmp" TMP="$WORK/tmp" TEMP="$WORK/tmp"
export XDG_CACHE_HOME="$WORK/cache" PIP_CACHE_DIR="$WORK/cache/pip"
export PIP_NO_INDEX=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$WORK/pycache" SOURCE_DATE_EPOCH=315532800
export PYTHONPATH="$ROOT/src"
if command -v pyenv >/dev/null 2>&1; then export PYENV_VERSION="3.11.12:3.13.13:system"; fi

python3 tools/check_public_scope.py
python3 -m compileall -q src tests examples tools
python3 -m unittest discover -s tests -v > "$WORK/tests-system.log" 2>&1

for py in python3.11 python3.13 python3.14; do
  if ! command -v "$py" >/dev/null 2>&1; then echo "NOT_AVAILABLE $py"; continue; fi
  version="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  "$py" -m unittest discover -s tests -v > "$WORK/tests-$version.log" 2>&1
  if [[ "$version" == "3.11" ]]; then
    "$py" -m pip wheel --no-index --no-deps --no-build-isolation -w "$WORK/wheel-a" . > "$WORK/wheel-a.log" 2>&1
    "$py" -c 'import scar_build_backend,sys; print(scar_build_backend.build_sdist(sys.argv[1]))' "$WORK/sdist" > "$WORK/sdist.log" 2>&1
    "$py" -m pip wheel --no-index --no-deps --no-build-isolation -w "$WORK/wheel-b" . > "$WORK/wheel-b.log" 2>&1
    cmp "$WORK/wheel-a/scar_research_toolkit-0.2.0-py3-none-any.whl" "$WORK/wheel-b/scar_research_toolkit-0.2.0-py3-none-any.whl"
    "$py" -c 'import scar_build_backend,sys; print(scar_build_backend.build_sdist(sys.argv[1]))' "$WORK/sdist-b" > "$WORK/sdist-b.log" 2>&1
    cmp "$WORK/sdist/scar_research_toolkit-0.2.0.tar.gz" "$WORK/sdist-b/scar_research_toolkit-0.2.0.tar.gz"
    "$py" -m pip wheel --no-index --no-deps --no-build-isolation -w "$WORK/sdist-wheel" "$WORK/sdist/scar_research_toolkit-0.2.0.tar.gz" > "$WORK/sdist-wheel.log" 2>&1
    "$py" -m venv "$WORK/venv-sdist"
    "$WORK/venv-sdist/bin/python" -m pip install --no-index --no-deps "$WORK/sdist-wheel/scar_research_toolkit-0.2.0-py3-none-any.whl" > "$WORK/sdist-install.log" 2>&1
    "$WORK/venv-sdist/bin/python" -m pip check >> "$WORK/sdist-install.log" 2>&1
    "$WORK/venv-sdist/bin/scar-kit" test >> "$WORK/sdist-install.log" 2>&1
    "$py" -m venv "$WORK/venv-direct-sdist"
    "$WORK/venv-direct-sdist/bin/python" -m pip install --no-index --no-build-isolation --no-deps "$WORK/sdist/scar_research_toolkit-0.2.0.tar.gz" > "$WORK/direct-sdist-install.log" 2>&1
    "$WORK/venv-direct-sdist/bin/python" -m pip check >> "$WORK/direct-sdist-install.log" 2>&1
    "$WORK/venv-direct-sdist/bin/scar-kit" test >> "$WORK/direct-sdist-install.log" 2>&1
    "$py" -m venv "$WORK/venv-direct-source"
    "$WORK/venv-direct-source/bin/python" -m pip install --no-index --no-build-isolation --no-deps . > "$WORK/direct-source-install.log" 2>&1
    "$WORK/venv-direct-source/bin/python" -m pip check >> "$WORK/direct-source-install.log" 2>&1
    "$WORK/venv-direct-source/bin/scar-kit" test >> "$WORK/direct-source-install.log" 2>&1
  fi
  venv="$WORK/venv-$version"
  "$py" -m venv "$venv"
  "$venv/bin/python" -m pip install --no-index --no-deps "$WORK/wheel-a/scar_research_toolkit-0.2.0-py3-none-any.whl" > "$WORK/install-$version.log" 2>&1
  "$venv/bin/python" -m pip check >> "$WORK/install-$version.log" 2>&1
  "$venv/bin/scar-kit" version >> "$WORK/install-$version.log" 2>&1
  "$venv/bin/scar-kit" test >> "$WORK/install-$version.log" 2>&1
  "$venv/bin/scar-kit" demo > "$WORK/demo-$version.log"
  if [[ "$version" == "3.11" ]]; then
    data="$($venv/bin/python -c 'from pathlib import Path; import scar_core; print(Path(scar_core.__file__).parent / "data/demo")')"
    "$venv/bin/scar-kit" inspect --input "$data/envelope.json" --root "$data" --format json > "$WORK/inspect-$version.json"
    "$venv/bin/scar-kit" explain --input "$data/envelope.json" --root "$data" > "$WORK/explain-$version.txt"
  fi
done

python3 tools/build_source_archive.py --output "$WORK/SCAR_RESEARCH_PUBLIC_REPOSITORY.zip" > "$WORK/archive-a.log"
python3 tools/verify_source_archive.py "$WORK/SCAR_RESEARCH_PUBLIC_REPOSITORY.zip"
python3 tools/build_source_archive.py --output "$WORK/source-rebuild.zip" > "$WORK/archive-b.log"
cmp "$WORK/SCAR_RESEARCH_PUBLIC_REPOSITORY.zip" "$WORK/source-rebuild.zip"
python3 tools/verify_source_archive.py "$WORK/source-rebuild.zip"
EXTRACT="$WORK/extracted"
mkdir -p "$EXTRACT"
python3 - "$WORK/SCAR_RESEARCH_PUBLIC_REPOSITORY.zip" "$EXTRACT" <<'PY'
import sys, zipfile
from pathlib import Path, PurePosixPath
archive, destination = map(Path, sys.argv[1:])
with zipfile.ZipFile(archive) as zf:
    for name in zf.namelist():
        p=PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or "\\" in name:
            raise SystemExit("unsafe archive path")
        target=destination.joinpath(*p.parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(zf.read(name))
PY
mkdir -p "$WORK/extracted-wheel"
PYTHONPATH="$EXTRACT" python3 -c 'import scar_build_backend,sys; print(scar_build_backend.build_sdist(sys.argv[1]))' "$WORK/extracted-sdist" > "$WORK/extracted-sdist.log" 2>&1
python3.11 -m pip wheel --no-index --no-deps --no-build-isolation -w "$WORK/extracted-wheel" "$EXTRACT" > "$WORK/extracted-wheel.log" 2>&1
PYTHONPATH="$EXTRACT/src" python3 -m unittest discover -s "$EXTRACT/tests" -v > "$WORK/extracted-tests.log" 2>&1
python3.11 -m venv "$WORK/venv-archive-replay"
"$WORK/venv-archive-replay/bin/python" -m pip install --no-index --no-deps "$WORK/extracted-wheel/scar_research_toolkit-0.2.0-py3-none-any.whl" > "$WORK/archive-replay-install.log" 2>&1
"$WORK/venv-archive-replay/bin/python" -m pip check >> "$WORK/archive-replay-install.log" 2>&1
"$WORK/venv-archive-replay/bin/scar-kit" test >> "$WORK/archive-replay-install.log" 2>&1
"$WORK/venv-archive-replay/bin/scar-kit" demo > "$WORK/archive-replay-demo.log"
python3 tools/check_public_scope.py
(cd "$WORK" && shasum -a 256 SCAR_RESEARCH_PUBLIC_REPOSITORY.zip > SCAR_RESEARCH_PUBLIC_REPOSITORY.zip.sha256)
echo "SCAR_RESEARCH_PUBLIC_REPOSITORY_VERIFY=PASS"
