#!/usr/bin/env bash
#
# Kortny one-line installer for a fresh Linux server (Ubuntu/Debian/EC2/DO/Hetzner).
#
#   curl -fsSL https://raw.githubusercontent.com/boffti/kortny/main/scripts/install.sh | bash
#
# Installs Docker if needed, fetches the published GHCR images, generates the
# required secrets, and brings up the full self-hosted stack WITH the code
# sandbox (the flagship capability that PaaS one-click buttons can't run, because
# they don't expose a Docker socket). Idempotent: safe to re-run.
#
set -euo pipefail

REPO_URL="https://github.com/boffti/kortny"
COMPOSE=(-f compose.yaml -f compose.prod.yaml)

c_info='\033[1;36m'; c_ok='\033[1;32m'; c_warn='\033[1;33m'; c_err='\033[1;31m'; c_off='\033[0m'
log()  { printf "${c_info}==>${c_off} %s\n" "$*"; }
ok()   { printf "${c_ok}✓${c_off} %s\n" "$*"; }
warn() { printf "${c_warn}!${c_off} %s\n" "$*"; }
die()  { printf "${c_err}✗${c_off} %s\n" "$*" >&2; exit 1; }

# --- 1. Prerequisites: Docker + Compose v2 -----------------------------------
command -v curl >/dev/null 2>&1 || die "curl is required."
if ! command -v git >/dev/null 2>&1; then
  if [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null 2>&1; then
    log "Installing git..."; sudo apt-get update -qq && sudo apt-get install -y -qq git
  else
    die "git is required; install it and re-run."
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  if [ "$(uname -s)" = "Linux" ]; then
    log "Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "${USER:-$(id -un)}" 2>/dev/null || true
    ok "Docker installed (group membership applies on next login)."
  else
    die "Docker not found. Install Docker Desktop (https://www.docker.com) and re-run."
  fi
fi

# Decide whether docker needs sudo in THIS shell (group change needs a re-login).
SUDO=""
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    SUDO="sudo"
  else
    die "Docker daemon not reachable. Start it (or re-login for group changes) and re-run."
  fi
fi
$SUDO docker compose version >/dev/null 2>&1 || die "Docker Compose v2 required (ships with modern Docker)."
dc() { $SUDO docker compose "${COMPOSE[@]}" "$@"; }

# --- 2. Source tree ----------------------------------------------------------
if [ -f compose.yaml ] && [ -f compose.prod.yaml ]; then
  log "Using current directory: $(pwd)"
else
  log "Cloning Kortny into ./kortny ..."
  git clone --depth 1 "$REPO_URL" kortny
  cd kortny
fi
[ -f .env.example ] || die "compose.prod.yaml present but .env.example missing — unexpected tree."

# --- 3. .env + secrets -------------------------------------------------------
if [ ! -f .env ]; then cp .env.example .env; ok "Created .env from .env.example"; fi

val_of()      { grep -E "^$1=" .env 2>/dev/null | head -1 | sed -E "s/^$1=//"; }
gen_secret()  { openssl rand -hex 32 2>/dev/null || head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
needs_secret() {
  case "$(val_of "$1")" in
    ""|*change*|*Change*|*CHANGE*|*placeholder*|*your-*|*your_*|*example*|*ci-only*|*xoxb-...*|*sk-...*) return 0;;
    *) return 1;;
  esac
}
set_env() { # set_env KEY VALUE  (replace in place or append; value printed literally)
  local key="$1" val="$2" tmp; tmp="$(mktemp)"
  if grep -qE "^${key}=" .env; then
    awk -v k="$key" -v v="$val" '$0 ~ "^"k"=" && !d {print k"="v; d=1; next} {print}' .env >"$tmp"
  else
    cat .env >"$tmp"; printf '%s=%s\n' "$key" "$val" >>"$tmp"
  fi
  mv "$tmp" .env
}

# The prod overlay refuses to boot with placeholder values for these.
for k in ENCRYPTION_KEY DASHBOARD_SESSION_SECRET; do
  if needs_secret "$k"; then set_env "$k" "$(gen_secret)"; ok "Generated $k"; fi
done
if needs_secret DASHBOARD_PASSWORD; then
  set_env DASHBOARD_PASSWORD "$(gen_secret | cut -c1-24)"; ok "Generated DASHBOARD_PASSWORD"
fi
if [ -z "$(val_of DASHBOARD_AUTH_MODE)" ]; then set_env DASHBOARD_AUTH_MODE password; fi

# --- 4. Optional: paste credentials now (else finish in the setup wizard) ----
required_keys="SLACK_BOT_TOKEN SLACK_APP_TOKEN SLACK_SIGNING_SECRET LLM_API_KEY LLM_MODEL COMPOSIO_API_KEY"
have_keys() { for k in $required_keys; do needs_secret "$k" && return 1; done; return 0; }

if [ -e /dev/tty ] && ! have_keys; then
  printf "\n${c_info}Optional:${c_off} paste your keys now for a fully-running stack, or press Enter to skip each and finish in the dashboard setup wizard.\n"
  printf "Create the Slack app first from this repo's ${c_info}manifest.json${c_off} (https://api.slack.com/apps → From Manifest).\n\n"
  ask() { # ask VAR "Prompt"
    local var="$1" msg="$2" ans
    needs_secret "$var" || return 0
    printf "%s " "$msg" >/dev/tty; IFS= read -r ans </dev/tty || ans=""
    [ -n "$ans" ] && set_env "$var" "$ans"
  }
  ask SLACK_BOT_TOKEN     "Slack Bot Token (xoxb-...):"
  ask SLACK_APP_TOKEN     "Slack App-Level Token (xapp-...):"
  ask SLACK_SIGNING_SECRET "Slack Signing Secret:"
  ask LLM_PROVIDER        "LLM provider [openai|anthropic|openrouter]:"
  ask LLM_API_KEY         "LLM API key:"
  ask LLM_MODEL           "LLM model (e.g. gpt-4o):"
  ask COMPOSIO_API_KEY    "Composio API key (required; enables 100+ integrations):"
fi

# --- 5. Pull images + bring up ----------------------------------------------
log "Pulling published images (ghcr.io/boffti/kortny:${KORTNY_VERSION:-latest})..."
dc pull

if have_keys; then
  log "Starting the full stack (with sandbox)..."
  dc up -d
  ok "Kortny is up."
  STAGE="full"
else
  log "Keys not set yet — starting Postgres + dashboard so you can finish in the setup wizard..."
  dc up -d postgres migrate dashboard
  STAGE="setup"
fi

# --- 6. Next steps -----------------------------------------------------------
ip="$(curl -fsSL https://api.ipify.org 2>/dev/null || echo your-server)"
printf "\n${c_ok}Done.${c_off}\n\n"
cat <<EOF
The dashboard binds to localhost for safety. Reach it from your machine via an SSH tunnel:

    ssh -L 8080:localhost:8080 <user>@${ip}
    # then open http://localhost:8080

EOF
if [ "$STAGE" = "setup" ]; then
  cat <<EOF
Finish setup:
  1. Create your Slack app from this repo's manifest.json (https://api.slack.com/apps → From Manifest).
  2. Open the dashboard (tunnel above) — it boots into a guided setup wizard that
     validates your Slack + LLM keys. Add them to .env on the server, then run:

         $SUDO docker compose -f compose.yaml -f compose.prod.yaml up -d

EOF
else
  cat <<EOF
Invite your bot in Slack and put it to work:
    /invite @your-bot-name
    @your-bot-name summarize the last 7 days of this channel

EOF
fi
printf "Generated secrets and config live in ${c_info}%s/.env${c_off} — keep it safe and back it up.\n" "$(pwd)"
printf "Front the dashboard with a reverse proxy before exposing it publicly (see docs/deployment.md).\n"
