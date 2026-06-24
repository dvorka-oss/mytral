#!/bin/bash
# Clean MyTraL snap build artifacts (temp build dir and output snap files).
# Does NOT remove build/snap/ source files.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Cleaning snap build artifacts..."
rm -rf "$PROJECT_ROOT/build/snap/project"
rm -rf "$PROJECT_ROOT/distro/snap"
rm -rf "$PROJECT_ROOT/parts" "$PROJECT_ROOT/prime" "$PROJECT_ROOT/stage" 2>/dev/null || true
echo "DONE"
