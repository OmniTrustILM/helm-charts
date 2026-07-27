#!/usr/bin/env bash
# Render and behavior tests for the ilm provision-instance-queue init container.
# Requires: helm, yq (Mike Farah v4), jq. Run from the repository root.
set -euo pipefail

CHART=charts/ilm
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "ok: $1"; }

for t in helm yq jq; do
  command -v "$t" > /dev/null || fail "required tool '$t' not found on PATH"
done

# --- preflight: umbrella dependencies present and lock consistent ---
helm dependency build "$CHART" --skip-refresh > /dev/null
git diff --exit-code -- "$CHART/Chart.lock" > /dev/null || fail "Chart.lock drifted after dependency build"

extract_script() {  # stdin: manifests; stdout: init container script
  yq ea 'select(.kind == "Deployment") | .spec.template.spec.initContainers[]? | select(.name == "provision-instance-queue") | .command[2]' -
}

render_script() {  # $@: helm value args; stdout: init container script
  helm template "$CHART" "$@" | extract_script
}

body_of() {  # $1: rendered script file, $2: empty run dir; prints BODY JSON
  awk '{print} /^BODY=\$\(printf/ {exit}' "$1" > "$2/part.sh"
  { echo 'hostname() { echo core-test-0; }'; cat "$2/part.sh"; echo 'printf "%s\n" "$BODY"'; } > "$2/harness.sh"
  ( cd "$2" && sh harness.sh )
}

# --- 1. default body is backward compatible ---
render_script --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true > "$WORK/default.sh"
[ -s "$WORK/default.sh" ] || fail "init container script not rendered"
mkdir "$WORK/run-default"
body_of "$WORK/default.sh" "$WORK/run-default" > "$WORK/default.json"
jq -e --argjson want '{"name":"core-test-0","exchange":"ilm-proxy","routingKey":"proxymessage.*.core-test-0","properties":{"x-expires":1800000}}' \
  '. == $want' "$WORK/default.json" > /dev/null || fail "default body drifted: $(cat "$WORK/default.json")"
pass "default body backward compatible"

# --- 2. saas-style override; a user-set properties map fully replaces the default ---
cat > "$WORK/saas.yaml" <<'YAML'
global:
  proxy:
    enabled: true
  provisioning:
    apiUrl: "http://provisioning.test:8080"
    apiKey: "test-key"
    queue:
      exchange: "customer-acme-proxies-topic"
      properties:
        autoDeleteOnIdle: "PT30M"
YAML
render_script -f "$WORK/saas.yaml" > "$WORK/saas.sh"
[ -s "$WORK/saas.sh" ] || fail "saas scenario did not render"
mkdir "$WORK/run-saas"
body_of "$WORK/saas.sh" "$WORK/run-saas" > "$WORK/saas.json"
jq -e --argjson want '{"name":"core-test-0","exchange":"customer-acme-proxies-topic","routingKey":"proxymessage.*.core-test-0","properties":{"autoDeleteOnIdle":"PT30M"}}' \
  '. == $want' "$WORK/saas.json" > /dev/null || fail "saas body wrong: $(cat "$WORK/saas.json")"
jq -e '.properties | has("x-expires") | not' "$WORK/saas.json" > /dev/null \
  || fail "RabbitMQ default x-expires leaked into an overridden properties map"
pass "saas override body correct (properties fully replaced)"

# --- 2b. explicit empty properties map is honoured ---
cat > "$WORK/emptyprops.yaml" <<'YAML'
global:
  proxy:
    enabled: true
  provisioning:
    apiUrl: "http://provisioning.test:8080"
    queue:
      exchange: "customer-acme-proxies-topic"
      properties: {}
YAML
render_script -f "$WORK/emptyprops.yaml" > "$WORK/emptyprops.sh"
[ -s "$WORK/emptyprops.sh" ] || fail "empty-properties scenario did not render"
mkdir "$WORK/run-empty"
body_of "$WORK/emptyprops.sh" "$WORK/run-empty" > "$WORK/empty.json"
jq -e '.properties == {}' "$WORK/empty.json" > /dev/null \
  || fail "explicit empty properties not honoured: $(jq -c .properties "$WORK/empty.json")"
pass "explicit empty properties honoured"

# --- 3. hostile characters pass through byte-exact without shell evaluation ---
cat > "$WORK/hostile.yaml" <<'YAML'
global:
  proxy:
    enabled: true
  provisioning:
    apiUrl: "http://provisioning.test:8080"
    queue:
      exchange: 'evil-$(touch pwned)-\back\slash-"quote-`tick`'
      properties:
        note: 'has $dollar and $(sub) and `tick` and \slash'
YAML
render_script -f "$WORK/hostile.yaml" > "$WORK/hostile.sh"
[ -s "$WORK/hostile.sh" ] || fail "hostile scenario did not render"
mkdir "$WORK/run-hostile"
body_of "$WORK/hostile.sh" "$WORK/run-hostile" > "$WORK/hostile.json"
[ ! -e "$WORK/run-hostile/pwned" ] || fail "shell executed \$() from a value"
jq -e . "$WORK/hostile.json" > /dev/null || fail "hostile body is not valid JSON: $(cat "$WORK/hostile.json")"
[ "$(jq -r .exchange "$WORK/hostile.json")" = 'evil-$(touch pwned)-\back\slash-"quote-`tick`' ] \
  || fail "exchange not byte-exact: $(jq -r .exchange "$WORK/hostile.json")"
[ "$(jq -r .name "$WORK/hostile.json")" = "core-test-0" ] || fail "hostname not substituted"
[ "$(jq -r .properties.note "$WORK/hostile.json")" = 'has $dollar and $(sub) and `tick` and \slash' ] \
  || fail "properties.note not byte-exact: $(jq -r .properties.note "$WORK/hostile.json")"
pass "hostile characters safe and byte-exact"

# --- 4. render-time validation ---
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set 'global.provisioning.queue.exchange=' > /dev/null 2>&1; then
  fail "empty exchange was not rejected"
fi
pass "empty exchange rejected"
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set 'global.provisioning.queue.routingKey=' > /dev/null 2>&1; then
  fail "empty routingKey was not rejected"
fi
pass "empty routingKey rejected"
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set 'global.provisioning.queue.properties=oops' > /dev/null 2>&1; then
  fail "scalar properties was not rejected"
fi
pass "scalar properties rejected"
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set 'global.provisioning.queue.properties=false' > /dev/null 2>&1; then
  fail "boolean false properties was not rejected"
fi
pass "boolean false properties rejected"
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set-json 'global.provisioning.queue.properties=[]' > /dev/null 2>&1; then
  fail "empty-array properties was not rejected"
fi
pass "empty-array properties rejected"
# absent properties still yields the built-in default
render_script --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true > "$WORK/absentprops.sh"
mkdir "$WORK/run-absentprops"
body_of "$WORK/absentprops.sh" "$WORK/run-absentprops" > "$WORK/absentprops.json"
jq -e '.properties == {"x-expires":1800000}' "$WORK/absentprops.json" > /dev/null \
  || fail "absent properties did not yield built-in default: $(jq -c .properties "$WORK/absentprops.json")"
pass "absent properties yields built-in default"
cat > "$WORK/badtype.yaml" <<'YAML'
global:
  proxy:
    enabled: true
  provisioning:
    apiUrl: "http://provisioning.test:8080"
    queue:
      exchange: 12345
YAML
if helm template "$CHART" -f "$WORK/badtype.yaml" > /dev/null 2>&1; then
  fail "non-string exchange was not rejected"
fi
pass "non-string exchange rejected"
if helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
     --set 'provisioningRabbitMq.bootstrap.proxy.exchange=custom-x' > /dev/null 2>&1; then
  fail "local exchange mismatch was not rejected"
fi
pass "local exchange mismatch rejected"
helm template "$CHART" --set global.proxy.enabled=true --set provisioningRabbitMq.enabled=true \
  --set 'provisioningRabbitMq.bootstrap.proxy.exchange=custom-x' \
  --set 'global.provisioning.queue.exchange=custom-x' > /dev/null \
  || fail "matching local exchange did not render"
pass "matching local exchange renders"

# --- 5. request loop behavior (stubbed curl/sleep) ---
mkdir "$WORK/stub"
cat > "$WORK/stub/curl" <<'SH'
#!/bin/sh
# Replays one line of $CURL_SCRIPT per call: "<http_code>|<curl_exit>|<body>".
# Mimics curl with -w '\n%{http_code}': prints body, newline, http code.
# When canned lines are exhausted, returns a permanent 4xx so the script
# under test fails fast instead of looping forever.
# Args are logged via printf (not echo: some /bin/sh builtins interpret
# backslash escapes like the literal \n in -w '\n%{http_code}', which would
# corrupt the one-line-per-call log) and any real newlines embedded in the
# multi-line JSON body are flattened so each invocation is exactly one line.
printf '%s ' "$@" | tr '\n' ' ' >> "$CURL_ARGS"
printf '\n' >> "$CURL_ARGS"
N=$(cat "$CURL_STATE" 2>/dev/null || echo 0); N=$((N+1)); printf '%s' "$N" > "$CURL_STATE"
LINE=$(sed -n "${N}p" "$CURL_SCRIPT")
[ -n "$LINE" ] || LINE='499|0|stub exhausted'
HTTP=${LINE%%|*}; REST=${LINE#*|}; RC=${REST%%|*}; B=${REST#*|}
printf '%s\n%s' "$B" "$HTTP"
exit "$RC"
SH
cat > "$WORK/stub/sleep" <<'SH'
#!/bin/sh
exit 0
SH
chmod +x "$WORK/stub/curl" "$WORK/stub/sleep"

run_loop() {  # $1: canned file, $2: api key ("" = none); sets LOOP_EXIT, writes $WORK/loop-out.txt + $WORK/loop-args
  : > "$WORK/loop-args"; rm -f "$WORK/loop-state"
  LOOP_EXIT=0
  # Run in the background under a bounded poll instead of blocking forever: if a
  # regression turns the permanent-4xx branch back into a retry, the synthetic
  # "stub exhausted" 499 would otherwise spin against the no-op sleep stub forever.
  env PATH="$WORK/stub:$PATH" \
      CURL_SCRIPT="$1" CURL_STATE="$WORK/loop-state" CURL_ARGS="$WORK/loop-args" \
      PROVISIONING_API_URL="http://stub" PROVISIONING_API_KEY="$2" \
      sh "$WORK/default.sh" > "$WORK/loop-out.txt" 2>&1 &
  pid=$!
  tries=0
  while kill -0 "$pid" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -gt 50 ]; then
      kill -9 "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      fail "run_loop scenario $1 did not terminate within the 5s budget — possible retry-loop regression"
    fi
    sleep 0.1
  done
  wait "$pid" || LOOP_EXIT=$?
}
requests() { wc -l < "$WORK/loop-args" | tr -d ' '; }

# A: transient 500 then 201 -> success after exactly one retry
printf '500|0|server boom\n201|0|{"ok":1}\n' > "$WORK/case-a.txt"
run_loop "$WORK/case-a.txt" ""
[ "$LOOP_EXIT" -eq 0 ] || fail "case A: expected exit 0, got $LOOP_EXIT: $(cat "$WORK/loop-out.txt")"
[ "$(requests)" -eq 2 ] || fail "case A: expected 2 requests, got $(requests)"
[ "$(grep -c 'retrying' "$WORK/loop-out.txt")" -eq 1 ] || fail "case A: expected 1 retry line"
grep -qF '"exchange": "ilm-proxy"' "$WORK/loop-args" || fail "case A: body not sent"
grep -qF -e '-d {' "$WORK/loop-args" || fail "case A: -d flag not associated with the body value"
pass "case A: 5xx retried then success"

# B: permanent 403 -> fail fast, response body printed
printf '403|0|{"error":"exchange does not belong to this customer"}\n' > "$WORK/case-b.txt"
run_loop "$WORK/case-b.txt" ""
[ "$LOOP_EXIT" -eq 1 ] || fail "case B: expected exit 1, got $LOOP_EXIT"
[ "$(requests)" -eq 1 ] || fail "case B: expected 1 request, got $(requests)"
grep -qF 'HTTP 403' "$WORK/loop-out.txt" || fail "case B: status not printed"
grep -qF 'does not belong' "$WORK/loop-out.txt" || fail "case B: response body not printed"
pass "case B: permanent 4xx fails fast with body"

# C: transport failures (curl exit 7) retried until success
printf '000|7|\n000|7|\n201|0|{}\n' > "$WORK/case-c.txt"
run_loop "$WORK/case-c.txt" ""
[ "$LOOP_EXIT" -eq 0 ] || fail "case C: expected exit 0, got $LOOP_EXIT: $(cat "$WORK/loop-out.txt")"
[ "$(requests)" -eq 3 ] || fail "case C: expected 3 requests, got $(requests)"
[ "$(grep -c 'curl exit 7' "$WORK/loop-out.txt")" -eq 2 ] || fail "case C: expected 2 transport-retry lines"
pass "case C: transport failures retried"

# D: API-key branch sends the header
printf '201|0|{}\n' > "$WORK/case-d.txt"
run_loop "$WORK/case-d.txt" "secret-key"
[ "$LOOP_EXIT" -eq 0 ] || fail "case D: expected exit 0, got $LOOP_EXIT"
grep -qF 'X-API-Key: secret-key' "$WORK/loop-args" || fail "case D: X-API-Key header not sent"
grep -qF -e '-H X-API-Key: secret-key' "$WORK/loop-args" || fail "case D: -H flag not associated with the X-API-Key value"
pass "case D: API key header sent"

# E: truncated transfer (HTTP 200 but curl exit 18) is a failure -> retried
printf '200|18|partial\n201|0|{}\n' > "$WORK/case-e.txt"
run_loop "$WORK/case-e.txt" ""
[ "$LOOP_EXIT" -eq 0 ] || fail "case E: expected exit 0, got $LOOP_EXIT: $(cat "$WORK/loop-out.txt")"
[ "$(requests)" -eq 2 ] || fail "case E: expected 2 requests, got $(requests)"
grep -qF 'curl exit 18' "$WORK/loop-out.txt" || fail "case E: transport failure not detected despite HTTP 200"
pass "case E: transport failure with HTTP status retried"

# F: permanent transport failure (curl exit 3, malformed URL) -> fail fast, no retry
printf '000|3|\n201|0|{}\n' > "$WORK/case-f.txt"
run_loop "$WORK/case-f.txt" ""
[ "$LOOP_EXIT" -eq 1 ] || fail "case F: expected exit 1, got $LOOP_EXIT: $(cat "$WORK/loop-out.txt")"
[ "$(requests)" -eq 1 ] || fail "case F: expected 1 request, got $(requests)"
grep -qF 'curl exit 3' "$WORK/loop-out.txt" || fail "case F: exit code not named in diagnostic"
grep -qF 'http://stub' "$WORK/loop-out.txt" || fail "case F: URL not named in diagnostic"
pass "case F: permanent curl exit code fails fast without retry"

echo "ALL PROVISION-QUEUE TESTS PASSED"
