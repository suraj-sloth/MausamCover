#!/usr/bin/env bash
# Demo incident for NudgeBee.
#   ./scripts/incident.sh break   -> bad APP_URL rolled out, pod crash-loops, oracle goes stale
#   ./scripts/incident.sh fix     -> manual fix (what the approved NudgeBee runbook should do)
#   ./scripts/incident.sh status
set -euo pipefail
NS=mausamcover
case "${1:-status}" in
  break)
    kubectl -n $NS patch configmap oracle-config --type merge -p '{"data":{"APP_URL":"htp://misconfigured"}}'
    kubectl -n $NS rollout restart deployment/weather-oracle ;;
  fix)
    kubectl -n $NS patch configmap oracle-config --type merge -p '{"data":{"APP_URL":"http://host.docker.internal:8080"}}'
    kubectl -n $NS rollout restart deployment/weather-oracle ;;
  status)
    kubectl -n $NS get pods -l app=weather-oracle
    kubectl -n $NS logs deployment/weather-oracle --tail=5 || true ;;
esac
