#!/bin/sh
# Test redeployment script.
# Simulates a successful redeploy by copying the reference version snapshot
# into place so check-version will report "clean" on the next poll.
cp /opt/boardfarm/agent/tests/ref-version.txt /tmp/ref-version.txt
echo "Deployed: copied ref-version.txt to /tmp/ref-version.txt"
