#!/bin/bash
# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

set -euo pipefail

# This script builds: upstream tarball > source deb > binary deb
#
# See:
#   Beginners guide:
#     http://packaging.ubuntu.com/html/packaging-new-software.html
#   Debian maintainers guide:
#     https://www.debian.org/doc/manuals/maint-guide/index.en.html
#     https://www.debian.org/doc/manuals/debmake-doc/index.en.html
#   Debian formal doc:
#     https://www.debian.org/doc/debian-policy/
#

#
# IMPORTANT INSTRUCTIONS:
#
# - This script cannot be run from inside a Git repository:
#   copy this script to ~/p/mytral/launchpad and run it from there
# - Launchpad release directory must exist:
#   ~/p/mytral/launchpad
# - MYTRAL_SRC must point to the MyTraL Git source directory to be released.
# - Set DRY_RUN=true to build packages without uploading to Launchpad.

export MYTRAL_SRC=/home/dvorka/p/mytral/git/mytral
export MYTRAL_RELEASE_DIR=/home/dvorka/p/mytral/launchpad
export MYTRAL_MAINTAINER_EMAIL
MYTRAL_MAINTAINER_EMAIL=$(python3 -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('${MYTRAL_SRC}/pyproject.toml').read_text())
print(data['project']['authors'][0]['email'])
")

# set to the highest patch number already uploaded for this release;
# the loop increments it before each build, so 0 > first build gets .1
PATCH_VERSION=12

# set to true to skip the final dput upload step
export DRY_RUN="${DRY_RUN:-false}"
#export DRY_RUN="true"

# ############################################################################
# # Check dependencies #
# ############################################################################

function checkDependencies() {
    local missing_deps=()
    local missing_config=()

    # check for required commands
    if ! command -v brz &> /dev/null; then
        missing_deps+=("brz")
    fi

    if ! command -v dput &> /dev/null; then
        missing_deps+=("dput")
    fi

    if ! command -v pbuilder-dist &> /dev/null; then
        missing_deps+=("ubuntu-dev-tools")
    fi

    if ! command -v debuild &> /dev/null; then
        missing_deps+=("devscripts")
    fi

    if ! dpkg -l debhelper &> /dev/null; then
        missing_deps+=("debhelper")
    fi

    # report missing dependencies
    if [ ${#missing_deps[@]} -gt 0 ]
    then
        echo "ERROR: Missing required dependencies:"
        for dep in "${missing_deps[@]}"; do
            echo "  - $dep"
        done
        echo ""
        echo "To install all required packages, run:"
        echo "  sudo apt-get install brz dput ubuntu-dev-tools devscripts debhelper pbuilder"
        exit 1
    fi

    # check if brz whoami is configured (fall back to reading config directly if brz is broken)
    if ! brz whoami &> /dev/null
    then
        if ! grep -qE '^email\s*=' ~/.config/breezy/breezy.conf 2>/dev/null; then
            missing_config+=("brz-whoami")
        fi
    fi

    # report missing configuration
    if [ ${#missing_config[@]} -gt 0 ]
    then
        echo "ERROR: Missing required configuration:"
        for cfg in "${missing_config[@]}"; do
            case $cfg in
                brz-whoami)
                    echo "  - Bazaar/Breezy identity not set"
                    echo "    Run: brz whoami \"Your Name <your.email@example.com>\""
                    ;;
            esac
        done
        exit 1
    fi

    # check for GPG key matching the maintainer email
    if ! gpg --list-secret-keys "${MYTRAL_MAINTAINER_EMAIL}" &> /dev/null
    then
        missing_config+=("gpg-key")
    fi

    # report missing GPG configuration
    if [ ${#missing_config[@]} -gt 0 ]
    then
        echo "ERROR: Missing required configuration:"
        for cfg in "${missing_config[@]}"
        do
            case $cfg in
                gpg-key)
                    echo "  - No GPG key found for: ${MYTRAL_MAINTAINER_EMAIL}"
                    echo ""
                    echo "    OPTION 1: Generate new GPG key:"
                    echo "      gpg --full-generate-key"
                    echo "      (Use: Martin Dvorak <${MYTRAL_MAINTAINER_EMAIL}>)"
                    echo ""
                    echo "    OPTION 2: Import key from old machine:"
                    echo "      On old machine: gpg --export-secret-keys ${MYTRAL_MAINTAINER_EMAIL} > ~/gpg-key.asc"
                    echo "      Transfer file securely, then: gpg --import ~/gpg-key.asc"
                    echo ""
                    echo "    After creating/importing key:"
                    echo "      - Upload to keyserver: gpg --keyserver keyserver.ubuntu.com --send-keys YOUR_KEY_ID"
                    echo "      - Add to Launchpad: https://launchpad.net/~ultradvorka/+editpgpkeys"
                    ;;
            esac
        done
        exit 1
    fi
}

# ############################################################################
# # Prepare MyTraL sources from Git #
# ############################################################################

function prepareSources() {
    local dest_dir="${1}"
    echo "Preparing MyTraL source from ${MYTRAL_SRC} into ${dest_dir}"

    if [ ! -d "${MYTRAL_SRC}" ]
    then
        echo "ERROR: MYTRAL_SRC directory not found: ${MYTRAL_SRC}"
        exit 1
    fi

    mkdir -p "${dest_dir}"
    # git archive exports only tracked files — no .git dir, no untracked artifacts
    git -C "${MYTRAL_SRC}" archive HEAD | tar -x -C "${dest_dir}"

    if [ -z "$(ls -A "${dest_dir}")" ]
    then
        echo "ERROR: git archive produced an empty directory: ${dest_dir}"
        exit 1
    fi
}

# ############################################################################
# # Create updated changelog #
# ############################################################################

function createChangelog() {
    local changelog_file="${1}"
    local timestamp
    timestamp=$(date "+%a, %d %b %Y %H:%M:%S")
    local tz
    tz=$(date +%z)
    echo "Changelog timestamp: ${timestamp} ${tz}"
    echo "mytral (${MYTRAL_FULL_VERSION}) ${UBUNTUVERSION}; urgency=low" > "${changelog_file}"
    echo "" >> "${changelog_file}"
    echo "  * ${MYTRAL_MSG}" >> "${changelog_file}"
    echo "" >> "${changelog_file}"
    echo " -- Martin Dvorak (Dvorka) <martin.dvorak@mindforger.com>  ${timestamp} ${tz}" >> "${changelog_file}"
    echo "" >> "${changelog_file}"
}

# ############################################################################
# # Create upstream orig tarball #
# ############################################################################

function createOrigTarball() {
    local src_dir_abs="${1}"   # absolute path to the source directory
    local tarball_abs="${2}"   # absolute path for the output .orig.tar.gz

    local parent_dir
    parent_dir="$(dirname "${src_dir_abs}")"
    local src_name
    src_name="$(basename "${src_dir_abs}")"

    tar czf "${tarball_abs}" -C "${parent_dir}" "${src_name}"
    echo "Created orig tarball: ${tarball_abs}"
}

# ############################################################################
# # Release for *ONE* particular Ubuntu version #
# ############################################################################

function releaseForParticularUbuntuVersion() {
    export UBUNTUVERSION="${1}"
    export MYTRAL_VERSION="${2}"
    export MYTRAL_MSG="${3}"

    # version scheme: 1.53.0-0ubuntu1~jammy1 (standard Ubuntu PPA convention)
    export MYTRAL_FULL_VERSION="${MYTRAL_VERSION}-0ubuntu1~${UBUNTUVERSION}1"
    # debian source dir uses hyphen: mytral-1.53.0
    local SRC_DIR_NAME="mytral-${MYTRAL_VERSION}"
    # debian orig tarball uses underscore: mytral_1.53.0.orig.tar.gz
    local ORIG_TARBALL_NAME="mytral_${MYTRAL_VERSION}.orig.tar.gz"
    local NOW
    NOW=$(date +%Y-%m-%d--%H-%M-%S)
    local BUILD_DIR_NAME="mytral-build-${UBUNTUVERSION}-${NOW}"

    # create isolated per-distro build directory
    mkdir "${BUILD_DIR_NAME}"
    local BUILD_DIR_ABS
    BUILD_DIR_ABS="$(pwd)/${BUILD_DIR_NAME}"

    local SRC_DIR_ABS="${BUILD_DIR_ABS}/${SRC_DIR_NAME}"
    local ORIG_TARBALL_ABS="${BUILD_DIR_ABS}/${ORIG_TARBALL_NAME}"

    # prepare sources from Git (no Bazaar)
    prepareSources "${SRC_DIR_ABS}"

    # create orig tarball BEFORE adding debian/ (upstream tarball must not contain debian/)
    createOrigTarball "${SRC_DIR_ABS}" "${ORIG_TARBALL_ABS}"

    # add debian/ and generate changelog
    cp -r "${MYTRAL_SRC}/build/ubuntu/debian" "${SRC_DIR_ABS}/"
    createChangelog "${SRC_DIR_ABS}/debian/changelog"

    # build signed source package
    cd "${SRC_DIR_ABS}"
    debuild -S -sa -d
    cd "${BUILD_DIR_ABS}"

    # build binary .deb locally for installation testing (unsigned, no clean chroot needed)
    echo -e "\n_ mytral local binary .deb build  ______________________________________________\n"
    cd "${SRC_DIR_ABS}"
    debuild -b -d -us -uc
    cd "${BUILD_DIR_ABS}"
    echo ""
    echo "Local .deb packages:"
    ls "${BUILD_DIR_ABS}"/*.deb
    echo ""
    echo "Install with:"
    echo "  sudo dpkg -i ${BUILD_DIR_ABS}/mytral_*.deb"
    echo "  or"
    echo "  sudo apt install ${BUILD_DIR_ABS}/mytral_*.deb"
    echo ""

    # upload source package to Launchpad PPA
    local CHANGES_FILE="mytral_${MYTRAL_FULL_VERSION}_source.changes"
    echo "Before dput push: $(pwd)"
    if [ "${DRY_RUN}" = "false" ]
    then
        dput "ppa:ultradvorka/sport" "${CHANGES_FILE}"
    else
        echo "DRY_RUN=true: skipping dput upload of ${CHANGES_FILE}"
    fi

    cd ..
}

# ############################################################################
# # Main #
# ############################################################################

echo "IMPORTANT: make sure your GPG key is configured and uploaded to Launchpad."
echo "IMPORTANT: make sure your SSH key is configured on Launchpad: https://launchpad.net/~ultradvorka/+editsshkeys"
echo -e "This script is expected to be copied to and run from: ${HOME}/p/mytral/launchpad\n\n"

# refuse to run from inside a Git repository
if git rev-parse --git-dir > /dev/null 2>&1
then
    echo "This script must NOT be run from inside a Git repository."
    echo "Copy it to ${HOME}/p/mytral/launchpad and run it from there."
    exit 1
fi

if [ ! -d "${MYTRAL_RELEASE_DIR}" ]
then
    echo "ERROR: release directory must exist: ${MYTRAL_RELEASE_DIR}"
    exit 1
fi

# check all required dependencies
checkDependencies

# read version dynamically from the source tree — strip any trailing 'dev' suffix
BASE_VERSION=$(python3 -c "
import sys
sys.path.insert(0, '${MYTRAL_SRC}/mytral')
import version
print(version.__version__.replace('dev', '').rstrip('.'))
")
echo "Releasing MyTraL version: ${BASE_VERSION}"

export MYTRAL_MSG="Release ${BASE_VERSION}"

# start GPG agent if not already running
GPG_AGENT_SOCK=$(gpgconf --list-dirs agent-socket 2>/dev/null || true)
if [ -S "${GPG_AGENT_SOCK}" ]
then
    echo "OK: GPG agent running."
else
    gpg-agent --daemon
fi

# https://en.wikipedia.org/wiki/Ubuntu_version_history
# https://wiki.ubuntu.com/Releases
# obsolete:
#   precise quantal saucy utopic vivid wily yakkety artful cosmic disco eoan
#   groovy hirsute impish oracular
# removed (build-time deps unavailable; cannot install Python 3.12 app either):
#   trusty (14.04): debhelper 9, no pybuild-plugin-pyproject, no python3-hatchling, Python 3.4
#   xenial (16.04): debhelper 10, no pybuild-plugin-pyproject, no python3-hatchling, Python 3.5
#   bionic (18.04): debhelper 11, no pybuild-plugin-pyproject, no python3-hatchling, Python 3.6
#   focal  (20.04): debhelper 12, no pybuild-plugin-pyproject, no python3-hatchling, Python 3.8
# current:
#   jammy noble plucky questing
# future:
#   resolute

# for UBUNTU_VERSION in noble
for UBUNTU_VERSION in jammy noble plucky questing resolute
do
    PATCH_VERSION=$((PATCH_VERSION + 1))
    VERSIONED_BASE_VERSION="${BASE_VERSION%.*}.${PATCH_VERSION}"
    echo "Releasing MyTraL for Ubuntu version: ${UBUNTU_VERSION} (${VERSIONED_BASE_VERSION})"
    releaseForParticularUbuntuVersion "${UBUNTU_VERSION}" "${VERSIONED_BASE_VERSION}" "${MYTRAL_MSG}"
done

# eof
