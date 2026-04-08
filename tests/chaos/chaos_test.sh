#!/usr/bin/env bash

set -euo pipefail

REPLICAS=(
  "http://localhost:3001"
  "http://localhost:3002"
  "http://localhost:3003"
  "http://localhost:3004"
  "http://localhost:3005"
)

SERVICES=("replica1" "replica2" "replica3" "replica4" "replica5")

GATEWAY="http://localhost:3000"
POLL_INTERVAL=0.5
ELECTION_TIMEOUT=15
REJOIN_TIMEOUT=10

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass_count=0
fail_count=0

log()   { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
pass()  { echo -e "${GREEN}  PASS:${NC} $*"; pass_count=$((pass_count + 1)); }
fail()  { echo -e "${RED}  FAIL:${NC} $*"; fail_count=$((fail_count + 1)); }
warn()  { echo -e "${YELLOW}  WARN:${NC} $*"; }
header(){ echo -e "\n${BOLD}--- $* ---${NC}"; }

query_state() {
  local url="$1"
  curl -sf --connect-timeout 2 --max-time 3 "${url}/state" 2>/dev/null || echo ""
}

get_field() {
  local json="$1"
  local field="$2"
  echo "$json" | jq -r ".$field // empty" 2>/dev/null || echo ""
}

header "PREFLIGHT CHECKS"

for cmd in curl jq docker; do
  if ! command -v "$cmd" &>/dev/null; then
    fail "Required command '$cmd' not found"
    exit 1
  fi
done
pass "All dependencies available"

if docker compose version &>/dev/null; then
  COMPOSE_CMD="docker compose"
elif docker-compose version &>/dev/null; then
  COMPOSE_CMD="docker-compose"
else
  fail "Docker Compose not found"
  exit 1
fi
pass "Docker Compose available"

if curl -sf --connect-timeout 3 "${GATEWAY}/health" &>/dev/null; then
  pass "Gateway reachable"
else
  warn "Gateway not reachable"
fi

header "STEP 1: IDENTIFY CURRENT LEADER"

leader_url=""
leader_index=-1
leader_term=-1
leader_node_id=""

for i in "${!REPLICAS[@]}"; do
  url="${REPLICAS[$i]}"
  json=$(query_state "$url")

  if [[ -z "$json" ]]; then
    log "  ${SERVICES[$i]} ($url) - ${RED}UNREACHABLE${NC}"
    continue
  fi

  state=$(get_field "$json" "state")
  term=$(get_field "$json" "term")
  node_id=$(get_field "$json" "node_id")

  log "  ${SERVICES[$i]} ($url) - state=${BOLD}${state}${NC} term=${term} node_id=${node_id}"

  if [[ "$state" == "leader" ]]; then
    leader_url="$url"
    leader_index=$i
    leader_term=$term
    leader_node_id="$node_id"
  fi
done

if [[ -z "$leader_url" ]]; then
  fail "No leader found"
  exit 1
fi

leader_service="${SERVICES[$leader_index]}"
pass "Leader identified: ${leader_service}"

header "STEP 2: KILL THE LEADER"

CONTAINER_ID=$($COMPOSE_CMD ps -q "$leader_service" 2>/dev/null || docker ps --filter "name=${leader_service}" -q 2>/dev/null)

if [[ -z "$CONTAINER_ID" ]]; then
  fail "Could not find container for ${leader_service}"
  exit 1
fi

docker stop "$CONTAINER_ID" --time 2 &>/dev/null

sleep 1
json=$(query_state "$leader_url")
if [[ -z "$json" ]]; then
  pass "Confirmed: ${leader_service} is unreachable"
else
  fail "${leader_service} is still responding"
fi

header "STEP 3: MONITOR REELECTION"

new_leader_url=""
new_leader_index=-1
new_leader_term=-1
new_leader_node_id=""
election_start=$(date +%s)
saw_candidate=false

while true; do
  elapsed=$(( $(date +%s) - election_start ))

  if (( elapsed >= ELECTION_TIMEOUT )); then
    break
  fi

  for i in "${!REPLICAS[@]}"; do
    if (( i == leader_index )); then
      continue
    fi

    url="${REPLICAS[$i]}"
    json=$(query_state "$url")

    if [[ -z "$json" ]]; then
      continue
    fi

    state=$(get_field "$json" "state")
    term=$(get_field "$json" "term")
    node_id=$(get_field "$json" "node_id")

    if [[ "$state" == "candidate" ]] && [[ "$saw_candidate" == false ]]; then
      log "  [CANDIDATE] ${SERVICES[$i]} at +${elapsed}s"
      saw_candidate=true
    fi

    if [[ "$state" == "leader" ]]; then
      new_leader_url="$url"
      new_leader_index=$i
      new_leader_term=$term
      new_leader_node_id="$node_id"
      log "  [LEADER] ${SERVICES[$i]} at +${elapsed}s"
      break 2
    fi
  done

  sleep "$POLL_INTERVAL"
done

if [[ -z "$new_leader_url" ]]; then
  fail "No new leader elected"
else
  pass "New leader elected: ${SERVICES[$new_leader_index]}"
fi

header "STEP 4: VERIFY NEW LEADER"

if (( new_leader_term > leader_term )); then
  pass "Term increased"
else
  fail "Term did not increase"
fi

leader_count=0
for i in "${!REPLICAS[@]}"; do
  if (( i == leader_index )); then
    continue
  fi

  json=$(query_state "${REPLICAS[$i]}")
  state=$(get_field "$json" "state")

  if [[ "$state" == "leader" ]]; then
    leader_count=$((leader_count + 1))
  fi
done

if (( leader_count == 1 )); then
  pass "Exactly 1 leader"
else
  fail "Expected 1 leader, found ${leader_count}"
fi

sleep 2
gw_response=$(curl -sf --connect-timeout 3 "${GATEWAY}/leader" 2>/dev/null || echo "")
if [[ -n "$gw_response" ]]; then
  gw_leader=$(echo "$gw_response" | jq -r '.leader // empty' 2>/dev/null)
  if [[ -n "$gw_leader" ]]; then
    pass "Gateway discovered new leader"
  else
    warn "Gateway returned no leader field"
  fi
else
  warn "Gateway not reachable"
fi

header "STEP 5: RESTART OLD LEADER"

docker start "$CONTAINER_ID" &>/dev/null

rejoin_start=$(date +%s)
old_node_back=false

while true; do
  elapsed=$(( $(date +%s) - rejoin_start ))

  if (( elapsed >= REJOIN_TIMEOUT )); then
    break
  fi

  json=$(query_state "$leader_url")
  if [[ -n "$json" ]]; then
    state=$(get_field "$json" "state")
    term=$(get_field "$json" "term")

    if [[ -n "$state" ]]; then
      old_node_back=true
      log "  ${leader_service} is back at +${elapsed}s"
      break
    fi
  fi

  sleep "$POLL_INTERVAL"
done

if [[ "$old_node_back" == true ]]; then
  pass "Old leader is back online"
else
  fail "Old leader did not come back"
fi

header "STEP 6: VERIFY REJOIN AS FOLLOWER"

sleep 3

json=$(query_state "$leader_url")
if [[ -z "$json" ]]; then
  fail "Cannot query old leader"
else
  state=$(get_field "$json" "state")
  term=$(get_field "$json" "term")

  if [[ "$state" == "follower" ]]; then
    pass "Old leader rejoined as FOLLOWER"
  else
    warn "Old leader is in state ${state}"
  fi

  if (( term >= new_leader_term )); then
    pass "Term is up to date"
  else
    fail "Term is stale"
  fi
fi

header "FINAL CLUSTER STATE"

final_leader_count=0
for i in "${!REPLICAS[@]}"; do
  json=$(query_state "${REPLICAS[$i]}")

  if [[ -z "$json" ]]; then
    log "  ${SERVICES[$i]}: ${RED}UNREACHABLE${NC}"
    continue
  fi

  state=$(get_field "$json" "state")
  term=$(get_field "$json" "term")
  node_id=$(get_field "$json" "node_id")

  tag="[NODE]"
  [[ "$state" == "leader" ]] && tag="[LEADER]" && final_leader_count=$((final_leader_count + 1))
  [[ "$state" == "candidate" ]] && tag="[CANDIDATE]"

  log "  ${tag} ${SERVICES[$i]} (${node_id}): state=${state} term=${term}"
done

if (( final_leader_count == 1 )); then
  pass "Cluster is healthy"
else
  fail "Cluster has ${final_leader_count} leaders"
fi

header "TEST SUMMARY"

total=$((pass_count + fail_count))
echo ""
echo -e "  ${GREEN}Passed: ${pass_count}${NC}"
echo -e "  ${RED}Failed: ${fail_count}${NC}"
echo -e "  Total:  ${total}"
echo ""

if (( fail_count == 0 )); then
  echo -e "  ${GREEN}${BOLD}ALL TESTS PASSED${NC}"
  exit 0
else
  echo -e "  ${RED}${BOLD}SOME TESTS FAILED${NC}"
  exit 1
fi
