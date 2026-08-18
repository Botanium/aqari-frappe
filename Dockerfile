# Aqari's private preview image is based on the pinned Frappe/ERPNext v16
# runtime used by the local and online manifests.  The image contains only
# this synthetic-only app; site data and credentials remain volume/config
# inputs at runtime.
ARG FRAPPE_IMAGE=frappe/erpnext:v16.32.3
FROM ${FRAPPE_IMAGE}

USER root
COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/aqari

USER frappe
RUN cd /home/frappe/frappe-bench \
    && bench pip install -e apps/aqari \
    && awk 'NF && $0 != "aqari" { print } END { print "aqari" }' sites/apps.txt > sites/apps.txt.tmp \
    && mv sites/apps.txt.tmp sites/apps.txt
