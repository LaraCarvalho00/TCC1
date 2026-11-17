#!/usr/bin/env bash
set -euo pipefail

# Terraform rejected the Registry's signing key. Check the official archive
# against the checksum verified in the module's lockfile.
version=2.0.0
checksum=7f1916e6524d60de87a7e9659af72fa672d96e8f8fdee9b4b5c12ee5cb616d6d
mirror="${RUNNER_TEMP:?}/runpod-provider"
provider_dir="$mirror/registry.terraform.io/runpod/runpod"
archive="terraform-provider-runpod_${version}_linux_amd64.zip"
mkdir -p "$provider_dir"
curl -fsSL --retry 3 "https://github.com/runpod/terraform-provider-runpod/releases/download/v${version}/$archive" -o "$provider_dir/$archive"
grep -Fq "\"zh:$checksum\"" infra/runpod/run/.terraform.lock.hcl
printf '%s  %s\n' "$checksum" "$provider_dir/$archive" | sha256sum --check
printf 'TCC_PROVIDER_MIRROR=%s\n' "$mirror" >> "${GITHUB_ENV:?}"
