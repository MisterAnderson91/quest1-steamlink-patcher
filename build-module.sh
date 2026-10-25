#!/bin/sh
# Build the Magisk module zip served by the test page (docs/beta/).
set -e
cd "$(dirname "$0")/magisk-module"
out=../docs/beta/q1_steamlink_usb.zip
rm -f "$out"
zip -q -r -X "$out" module.prop customize.sh service.sh uninstall.sh META-INF
echo "wrote docs/beta/q1_steamlink_usb.zip ($(sed -n 's/^version=//p' module.prop))"
