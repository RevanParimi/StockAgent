#!/usr/bin/env bash
# auto_continue.sh - run the PI "continue" loop unattended on the owner's dev box.
#
# Each phase is a NEW non-interactive Claude Code session (`claude -p`), so an
# implementation and its review never share a conversation (AGENTS.md, REVIEW.md).
# Every phase ends with a `LOOP:` line (AGENTS.md, "Unattended loop runs"). The loop
# starts the next phase on `LOOP: NEXT` and stops on `LOOP: STOP`, a missing line, an
# error, a timeout, origin/main moving, the phase cap or a PAUSE file. It never pushes.
#
# Usage:
#   auto_continue.sh start  [--target ID] [--max-phases N]  run in tmux session "loop"
#   auto_continue.sh run    [--target ID] [--max-phases N]  run in this terminal
#   auto_continue.sh pause                                   stop after the current phase
#   auto_continue.sh resume [--target ID] [--max-phases N]  clear PAUSE, then start
#   auto_continue.sh status                                  running or not; recent log
#
# Settings live in ~/.autocontinue/config (chmod 600; never in git). All optional:
#   NTFY_TOPIC, NTFY_SERVER        phone notifications through ntfy
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   or through a Telegram bot
#   LOOP_MODEL (opus), LOOP_EFFORT (xhigh), PHASE_TIMEOUT (4h), MAX_PHASES (6)
#   LIMIT_WAIT (1800 s) and LIMIT_MAX_WAITS (12): how a usage limit is waited out
#   LOOP_ALLOW_LOCAL_COMMIT (0): 1 lets a phase commit accepted work locally, never push
set -euo pipefail

SELF="$(readlink -f "$0")"
REPO="${REPO:-$HOME/project/StockAgent}"
STATE_DIR="${STATE_DIR:-$HOME/.autocontinue}"
LOG_DIR="$STATE_DIR/logs"
PAUSE_FILE="$STATE_DIR/PAUSE"
mkdir -p "$LOG_DIR"
# shellcheck disable=SC1091
[ -f "$STATE_DIR/config" ] && . "$STATE_DIR/config"

LOOP_MODEL="${LOOP_MODEL:-opus}"
LOOP_EFFORT="${LOOP_EFFORT:-xhigh}"
PHASE_TIMEOUT="${PHASE_TIMEOUT:-4h}"
MAX_PHASES="${MAX_PHASES:-6}"
LIMIT_WAIT="${LIMIT_WAIT:-1800}"
LIMIT_MAX_WAITS="${LIMIT_MAX_WAITS:-12}"
TARGET=""
export PATH="$REPO/.stockai/bin:$HOME/.local/bin:$PATH"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$STATE_DIR/loop.log"; }

ascii() { printf '%s' "$1" | LC_ALL=C tr -cd '\40-\176' | cut -c1-80; }

notify() {  # $1 = title, $2 = body. A failed notification never stops the loop.
  local title body
  title="$(ascii "$1")"
  body="${2:0:3000}"
  if [ -n "${NTFY_TOPIC:-}" ]; then
    curl -fsS -m 15 -H "Title: $title" --data-binary "$body" \
      "${NTFY_SERVER:-https://ntfy.sh}/$NTFY_TOPIC" >/dev/null 2>&1 || log "notify: ntfy failed"
  fi
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -fsS -m 15 --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
      --data-urlencode "text=$title"$'\n'"$body" \
      "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" >/dev/null 2>&1 \
      || log "notify: telegram failed"
  fi
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --target) TARGET="${2:?--target needs a story id}"; shift 2 ;;
      --max-phases) MAX_PHASES="${2:?--max-phases needs a number}"; shift 2 ;;
      *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
  done
}

build_prompt() {
  local commit_rule="The owner does not allow commits in this run."
  [ "${LOOP_ALLOW_LOCAL_COMMIT:-0}" = 1 ] \
    && commit_rule="The owner allows a local commit of work accepted in this phase. Never push."
  printf '%s\n' "continue" "" \
    "This is an unattended loop run on the owner's dev box: nobody is watching." \
    "Follow AGENTS.md, including the section \"Unattended loop runs\"." \
    "$commit_rule" \
    "Stop target: ${TARGET:-none}."
}

# True when origin/main has commits this checkout lacks (someone pushed from the laptop).
main_moved() {
  if ! git -C "$REPO" fetch -q origin main 2>/dev/null; then
    log "git fetch failed; carrying on with the local state"
    return 1
  fi
  [ -n "$(git -C "$REPO" rev-list HEAD..origin/main 2>/dev/null)" ]
}

is_limit() { grep -qiE 'usage limit|limit reached|hit your .*limit|session limit|weekly limit|resets? (at|in) ' <<<"$1"; }

# Runs one phase. Sets LAST_JSON, RESULT_TEXT and IS_ERROR; returns the exit code.
run_phase() {
  local rc=0
  LAST_JSON="$LOG_DIR/$(date +%Y%m%d-%H%M%S).json"
  ( cd "$REPO" && timeout --signal=INT --kill-after=2m "$PHASE_TIMEOUT" \
      claude -p "$(build_prompt)" --output-format json \
        --name "loop $(date +%m%d-%H%M)" --model "$LOOP_MODEL" --effort "$LOOP_EFFORT" \
        --permission-mode auto --permission-prompts none \
        --disallowedTools "Bash(git push *)" "Bash(railway *)" \
  ) >"$LAST_JSON" 2>>"$STATE_DIR/claude.stderr" || rc=$?
  RESULT_TEXT="$(jq -r '.result // empty' "$LAST_JSON" 2>/dev/null || true)"
  IS_ERROR="$(jq -r '.is_error // false' "$LAST_JSON" 2>/dev/null || echo true)"
  return "$rc"
}

stop_loop() {  # $1 = reason, $2 = briefing
  log "loop stop: $1"
  notify "Loop stopped: $1" "$2"
}

loop() {
  exec 9>"$STATE_DIR/lock"
  flock -n 9 || { echo "The loop is already running ($SELF status)." >&2; exit 1; }
  local phases=0 waits=0 rc line brief
  log "loop start: target=${TARGET:-none} max_phases=$MAX_PHASES model=$LOOP_MODEL effort=$LOOP_EFFORT"
  notify "Loop started" "Target: ${TARGET:-none}. Up to $MAX_PHASES phases."
  while :; do
    if [ -f "$PAUSE_FILE" ]; then stop_loop "paused" "The PAUSE file is present."; return; fi
    if [ "$phases" -ge "$MAX_PHASES" ]; then
      stop_loop "phase cap" "Ran $phases phases, the cap for this run."; return
    fi
    if main_moved; then
      stop_loop "main moved" "origin/main has commits this checkout lacks. Sync the box (git pull), then resume."
      return
    fi
    log "phase $((phases + 1)): start (HEAD $(git -C "$REPO" rev-parse --short HEAD), $(git -C "$REPO" status --porcelain | wc -l) changed paths)"
    rc=0
    run_phase || rc=$?
    if [ "$rc" -eq 124 ]; then
      stop_loop "timeout" "The phase ran past $PHASE_TIMEOUT. Log: $LAST_JSON"; return
    fi
    if [ "$rc" -ne 0 ] || [ "$IS_ERROR" = true ]; then
      if is_limit "$RESULT_TEXT $(tail -n 5 "$STATE_DIR/claude.stderr" 2>/dev/null)"; then
        waits=$((waits + 1))
        if [ "$waits" -gt "$LIMIT_MAX_WAITS" ]; then
          stop_loop "usage limit" "Still limited after $LIMIT_MAX_WAITS waits."; return
        fi
        log "usage limit: waiting ${LIMIT_WAIT}s ($waits of $LIMIT_MAX_WAITS), then retrying the same phase"
        [ "$waits" -eq 1 ] && notify "Usage limit" "Waiting for the usage window; retrying every $((LIMIT_WAIT / 60)) min."
        sleep "$LIMIT_WAIT"
        continue
      fi
      stop_loop "error" "Claude ended with an error (exit $rc). Log: $LAST_JSON"$'\n'"${RESULT_TEXT:0:800}"
      return
    fi
    waits=0
    phases=$((phases + 1))
    # The last LOOP line decides; backticks or bold around it are tolerated.
    line="$(printf '%s\n' "$RESULT_TEXT" | grep -E '^[`*_ ]*LOOP: (NEXT|STOP)' | tail -n 1 \
      | sed -E 's/^[`*_ ]+//; s/[`*_ ]+$//' || true)"
    brief="$(printf '%s\n' "$RESULT_TEXT" | grep -vE '^[`*_ ]*LOOP: ' | tail -n 25 || true)"
    case "$line" in
      "LOOP: NEXT"*)
        log "phase $phases: NEXT"
        notify "Phase $phases done, continuing" "$brief" ;;
      "LOOP: STOP"*)
        stop_loop "$(printf '%s' "${line#LOOP: STOP}" | sed 's/^ *| *//')" "$brief"; return ;;
      *)
        stop_loop "no LOOP line" "The phase ended without a LOOP line, so the loop stopped to be safe."$'\n'"$brief"
        return ;;
    esac
  done
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift
case "$cmd" in
  run)
    parse_args "$@"
    loop ;;
  start)
    parse_args "$@"
    if tmux has-session -t loop 2>/dev/null; then echo "tmux session 'loop' already exists." >&2; exit 1; fi
    tmux new -d -s loop "$(printf '%q ' bash "$SELF" run "$@")"
    echo "Started in tmux session 'loop'. Watch: tmux attach -t loop (leave: Ctrl+b d)." ;;
  pause)
    touch "$PAUSE_FILE"
    echo "The loop stops before its next phase. A running phase finishes first." ;;
  resume)
    rm -f "$PAUSE_FILE"
    exec bash "$SELF" start "$@" ;;
  status)
    if flock -n "$STATE_DIR/lock" true 2>/dev/null; then echo "not running"; else echo "running"; fi
    [ -f "$PAUSE_FILE" ] && echo "PAUSE file present"
    tail -n 15 "$STATE_DIR/loop.log" 2>/dev/null || true ;;
  *)
    sed -n '2,24p' "$SELF"
    exit 2 ;;
esac
