#!/usr/bin/env bash

echo "PUSH production data from Git repo & sync BLOBs from the shared drive..."

# FROM:
_MYTRAL_DATA_DIR="${HOME}/.local/share/mytral/data"
# TO:
_SHARED_BLOBS_DIR="${HOME}/insync/_mytral_/production_data"

cd ${_MYTRAL_DATA_DIR} || exit 1

ls -d */ | \
while read -r MYTRAL_USR_DIR
do
  echo "  Syncing MyTraL user dir ${MYTRAL_USR_DIR%/} ..."
    FROM_DIR="${_MYTRAL_DATA_DIR}/${MYTRAL_USR_DIR%/}/blobs"
    TO_DIR="${_SHARED_BLOBS_DIR}/${MYTRAL_USR_DIR%/}/blobs"
    # TODO when all blobs ready: rsync -av --delete "${FROM_DIR}/" "${TO_DIR}/"
    cp -r "${FROM_DIR}/" "${TO_DIR}/"
done

echo "DONE: BLOBs synchronization."

# eof
