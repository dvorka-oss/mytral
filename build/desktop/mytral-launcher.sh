#!/bin/bash
# MyTraL Desktop Launcher
#
# This script can be used to create a desktop launcher for MyTraL
# after the executable has been built.

MYTRAL_EXECUTABLE="$HOME/.local/bin/mytral"

# check if executable exists
if [ ! -f "$MYTRAL_EXECUTABLE" ]; then
    echo "MyTraL executable not found at: $MYTRAL_EXECUTABLE"
    echo "Please build and install MyTraL first:"
    echo "  make distro-desktop-build"
    echo "  cp distro/desktop/mytral $MYTRAL_EXECUTABLE"
    exit 1
fi

# launch MyTraL desktop
MYTRAL_USER_REGISTRATION=true MYTRAL_INCARNATION=DESKTOP exec "$MYTRAL_EXECUTABLE" "$@"
