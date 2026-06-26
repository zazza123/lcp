set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
for t in test_config_reader.sh test_resolution.sh test_generate_config.sh test_manifest.sh; do
  echo "== $t =="; bash "$HERE/$t"
done
echo "ALL PLUGIN TESTS PASSED"
