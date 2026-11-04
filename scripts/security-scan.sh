#!/bin/sh
# DevSecOps checks. Jenkins runs this after building the images; it also runs
# locally from the repo root (Git Bash / Linux / macOS):  sh scripts/security-scan.sh
#
#   1. Secrets       gitleaks   - the working tree AND the whole git history
#   2. Dependencies  trivy fs   - known CVEs in pinned Python/npm dependencies
#      + IaC         trivy fs   - misconfigured Dockerfiles
#   3. Images        trivy      - OS and library CVEs in every image we build
#   4. SBOM          trivy      - a CycloneDX bill of materials per image (archived)
#
# Policy (fails the build): any secret; a HIGH/CRITICAL misconfiguration; a
# CRITICAL CVE that has a fix. Accepted risks live in .trivyignore.yaml, each with a reason.
#
# Sources reach the scanners through stdin (tar), never bind mounts, so this
# works from a Jenkins container using the host's Docker (Docker-outside-of-Docker).
# Only tracked or unignored files are sent: .env and deploy/secrets.yml never leave.
set -u
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: keep container paths like /var/run/docker.sock as they are
PROJECT="${COMPOSE_PROJECT_NAME:-chaosos}"
OUT=security-reports
GITLEAKS=zricethezav/gitleaks:v8.21.2
TRIVY=aquasec/trivy:0.56.2
CACHE="-v chaosos-trivy-cache:/root/.cache"   # vulnerability DB, reused between builds
LIMIT="--cpus 1"                              # leave the lab its CPU
IMAGES="api frontend traffic controller postgres"
mkdir -p "$OUT"
failed=""

sources() {
  { git ls-files -co --exclude-standard -z; printf '.git\0'; } | tar --null -T - -cf -
}

echo "== 1/4 Secrets: gitleaks (working tree + full git history)"
# gitleaks logs findings (redacted) to stderr; the history report (JSON) goes to stdout.
sources | docker run --rm -i $LIMIT --entrypoint sh "$GITLEAKS" -c '
  mkdir /src && tar -xf - -C /src && cd /src && git config --global --add safe.directory /src &&
  gitleaks detect --source . --config .gitleaks.toml --redact --no-banner \
    --report-format json --report-path /dev/stdout; history=$?
  gitleaks detect --no-git --source . --config .gitleaks.toml --redact --no-banner >&2; tree=$?
  exit $((history | tree))' > "$OUT/gitleaks.json" || failed="$failed secrets"

echo "== 2/4 Dependencies and Dockerfiles: trivy fs"
sources | docker run --rm -i $LIMIT $CACHE --entrypoint sh "$TRIVY" -c '
  mkdir /src && tar -xf - -C /src && cd /src &&
  trivy fs --quiet --scanners vuln,misconfig --include-dev-deps --severity HIGH,CRITICAL \
    --ignore-unfixed --ignorefile .trivyignore.yaml --exit-code 1 .' > "$OUT/trivy-fs.txt" 2>&1 \
  || failed="$failed dependencies/iac"
cat "$OUT/trivy-fs.txt"

echo "== 3/4 Images: trivy image (fail on fixable CRITICAL)   4/4 SBOM: CycloneDX"
# trivy_image <image> <args>: the accepted-risk file travels on stdin, like the sources.
trivy_image() {
  image="$1"; shift
  docker run --rm -i $LIMIT $CACHE -v /var/run/docker.sock:/var/run/docker.sock --entrypoint sh "$TRIVY" \
    -c 'cat > /tmp/ignore.yaml && exec trivy image --quiet --ignorefile /tmp/ignore.yaml "$@"' trivy \
    "$@" "$image" < .trivyignore.yaml
}
for svc in $IMAGES; do
  image="$PROJECT-$svc"
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "  $image: not built, skipped"; continue
  fi
  report="$OUT/trivy-image-$svc.txt"
  if trivy_image "$image" --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed > "$report" 2>&1; then
    trivy_image "$image" --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 >/dev/null 2>&1 \
      || failed="$failed image:$svc"
    trivy_image "$image" --format cyclonedx > "$OUT/sbom-$svc.cdx.json" 2>/dev/null
    totals=$(grep -E '^Total:' "$report" | sed 's/^Total: //' | tr '\n' ';' | sed 's/;$//')
    echo "  $image: fixable HIGH/CRITICAL per target: ${totals:-none}"
  else
    echo "  $image: scan error (see $report)"
    failed="$failed image:$svc"
  fi
done

if [ -n "$failed" ]; then
  echo "SECURITY SCAN FAILED:$failed (reports in $OUT/)"
  exit 1
fi
echo "SECURITY SCAN PASSED (reports and SBOMs in $OUT/)"
