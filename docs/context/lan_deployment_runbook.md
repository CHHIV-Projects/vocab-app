# Vocab App LAN Deployment Runbook

This runbook describes the accepted Vocab App deployment on the private LAN and the approved private tailnet access path. It is not a product-data update procedure and does not authorize public exposure.

Run command blocks in one Bash session; later blocks reuse `ENV_FILE`, `APP_ID`, `DB_ID_BEFORE`, and `ROLLBACK_TAG`. If starting a new session, redefine/recapture those variables as shown. Do not `source` the runtime env file.

## Canonical runtime identity

| Item | Canonical value |
|---|---|
| Checkout | `/home/chuck/projects/vocab-app`, branch `main` |
| Compose project | `vocab-app` |
| Application service | `vocab-app` |
| Database service | `vocab-db` |
| Learner endpoint | `http://192.168.1.173:8501/` |
| Health endpoint | `http://192.168.1.173:8501/_stcore/health` |
| Local Serve backend | `http://127.0.0.1:8501/` |
| Runtime environment file | `/home/chuck/.config/vocab-app/runtime.env` |
| Database storage | Persistent Docker volume `vocab_postgres_data` |
| Lexical/WordNet mounts | Host data mounted read-only in the app container |

Ports 8502, 8503, and 8504 have been used by temporary acceptance instances. They are not canonical production endpoints. Do not confuse a healthy test instance with the Compose project or container serving port 8501.

Private mobile access uses the server's Tailscale Serve HTTPS name reported by `tailscale serve status`:

```text
https://henderson-server1.tailba8d47.ts.net/
```

Serve proxies only to `http://127.0.0.1:8501/` and is tailnet-only. Do not infer accessibility from the hostname alone; the Product Owner must verify the same URL on the physical iPhone over Wi-Fi and cellular with Tailscale enabled, then verify it is unreachable with Tailscale disabled.

## Safety boundaries

- Use the explicit environment-file option for every Compose command. Never print, source into an interactive shell, copy, or commit the file or any secret value.
- Never use `docker compose down`, `down -v`, volume deletion, PostgreSQL recreation/reinitialization, or direct writes to the mounted lexical data.
- Deployment and controlled restart commands below target only `vocab-app`, with `--no-deps` where applicable. Do not rebuild, recreate, or restart `vocab-db`.
- If the repository, bind address, services, environment file, or production topology differs from this runbook, stop and resolve the discrepancy before deployment.
- The Compose app is bound explicitly to `192.168.1.173:8501` for LAN use and `127.0.0.1:8501` for the Tailscale Serve backend. Never replace these with `0.0.0.0:8501`.
- Tailscale Serve is the specifically approved private tailnet access layer for Vocab. Tailscale Funnel remains prohibited. Public reverse proxies, router port forwarding, and other public exposure remain prohibited.
- Tailnet access controls remain authoritative. Do not alter Tailscale ACLs, configure an exit node, change the iPhone's general Internet routing, or enable unrelated services.

## Pre-deployment checks

Run from the canonical checkout:

```bash
set -euo pipefail
cd /home/chuck/projects/vocab-app
git branch --show-current
git rev-parse HEAD
git status --short
```

Confirm branch `main` and the exact Product-Owner-accepted revision. Review every status entry. An active Repo Control workflow sidecar may be untracked; it is not application source, but only the sidecar identified by current Repo Control state may be treated as such. Stop on any other unexpected source/configuration drift. Do not stage, discard, or clean files to make the tree appear acceptable.

Check the secret file without displaying its contents:

```bash
set -euo pipefail
ENV_FILE=/home/chuck/.config/vocab-app/runtime.env
test -f "$ENV_FILE"
test "$(stat -c '%a' "$ENV_FILE")" = 600
awk -F= '/^[[:space:]]*(export[[:space:]]+)?VOCAB_DB_PASSWORD[[:space:]]*=/ {found=1} END {exit !found}' "$ENV_FILE"
```

The final command must exit successfully; it does not print the value. Compose has defaults for `VOCAB_DB_NAME` and `VOCAB_DB_USER`, but requires `VOCAB_DB_PASSWORD`. If a check fails, stop; do not improvise credentials.

Validate the resolved Compose configuration without printing it, then inspect service state:

```bash
set -euo pipefail
docker compose --env-file "$ENV_FILE" -p vocab-app config --quiet
docker compose --env-file "$ENV_FILE" -p vocab-app ps --all
docker inspect --format '{{.Name}} image={{.Image}} restart={{.HostConfig.RestartPolicy.Name}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
  vocab-app-vocab-app-1 vocab-app-vocab-db-1
```

Confirm the application is bound only to the explicit approved addresses `192.168.1.173:8501` and `127.0.0.1:8501`, both Compose services are the expected project/services, and PostgreSQL is healthy. The app initializes the migration runner at startup, so verify that all committed migration filenames are already recorded before proceeding; this milestone does not authorize schema changes:

```bash
set -euo pipefail
EXPECTED_MIGRATIONS="$(find db/migrations -maxdepth 1 -type f -name '*.sql' -printf '%f\n' | sed 's/\.sql$//' | sort)"
APPLIED_MIGRATIONS="$(docker exec vocab-app-vocab-db-1 sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version FROM schema_migrations ORDER BY version"'
)"
test "$EXPECTED_MIGRATIONS" = "$APPLIED_MIGRATIONS"
```

The database query prints only migration identifiers, not credentials or learner data. The equality check stops if the migration ledger is missing, if a committed migration is unapplied, or if an unexpected ledger version exists; resolve that separately with explicit Product Owner authorization.

Record the current app image ID and database container ID before deployment. Preserve the previous image for rollback only when it is known to be Product-Owner-accepted:

```bash
set -euo pipefail
PREVIOUS_IMAGE_ID="$(docker inspect --format '{{.Image}}' vocab-app-vocab-app-1)"
ROLLBACK_TAG="vocab-app-vocab-app:rollback-$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
docker image tag "$PREVIOUS_IMAGE_ID" "$ROLLBACK_TAG"
printf 'previous-image=%s rollback-tag=%s\n' "$PREVIOUS_IMAGE_ID" "$ROLLBACK_TAG"
```

Record the image ID and local rollback tag in the non-secret deployment record. The database volume is persistent; do not modify it.

## App-only deploy

The command rebuilds/recreates only the application service. `--no-deps` prevents Compose from acting on PostgreSQL:

```bash
set -euo pipefail
docker compose --env-file "$ENV_FILE" -p vocab-app \
  up -d --build --no-deps --force-recreate vocab-app
```

`--force-recreate` ensures the service adopts the newly built image even if Compose otherwise reports the existing container as already running. If the build or recreate fails, do not attempt database or destructive recovery. Inspect the app service and its logs; preserve the existing database and escalate if the failure does not have a safe, bounded resolution.

## Bounded health check

The app may report `starting` immediately after recreate. Poll for up to two minutes; do not interpret the first connection refusal as final failure:

```bash
set -euo pipefail
APP_ID="$(docker compose --env-file "$ENV_FILE" -p vocab-app ps -q vocab-app)"
test -n "$APP_ID"
for attempt in $(seq 1 24); do
  HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$APP_ID")"
  [ "$HEALTH" = healthy ] && break
  if [ "$HEALTH" = unhealthy ] || [ "$HEALTH" = missing ]; then
    docker logs --tail 100 "$APP_ID"
    exit 1
  fi
  sleep 5
done
test "$(docker inspect --format '{{.State.Health.Status}}' "$APP_ID")" = healthy
curl --fail --silent --show-error --max-time 5 \
  http://192.168.1.173:8501/_stcore/health
```

If health does not converge, inspect the bounded app logs and current Compose state, then stop. Do not restart PostgreSQL, remove volumes, or modify lexical data as a recovery shortcut.

Both explicitly published host paths must respond:

```bash
set -euo pipefail
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8501/_stcore/health
curl --fail --silent --show-error --max-time 5 http://192.168.1.173:8501/_stcore/health
```

## Source parity

Health alone does not establish which source is running. Compare the checked-out runtime files with their deployed copies. The list covers every Python module copied by the current Dockerfile and the SQL migrations used by the app. Each mismatch must fail the check:

```bash
set -euo pipefail
for path in app.py vocab_dictionary.py vocab_domain.py vocab_nlp.py \
  vocab_lexical_engine.py vocab_migrations.py vocab_workflow.py \
  vocab_persistence.py vocab_translation.py db/migrations/*.sql; do
  HOST_HASH="$(sha256sum "$path" | awk '{print $1}')"
  CONTAINER_HASH="$(docker exec "$APP_ID" sha256sum "/app/$path" | awk '{print $1}')"
  printf '%s %s\n' "$path" "$HOST_HASH"
  test "$HOST_HASH" = "$CONTAINER_HASH" || {
    printf 'Source parity failure: %s\n' "$path" >&2
    exit 1
  }
done
```

`requirements.txt` and `Dockerfile` are reviewed build inputs but are not copied into the current runtime image, so they do not have a container-file hash to compare. Record the accepted Git revision and deployed Docker image ID alongside the runtime-file parity result. A Git revision or image ID alone is not file-level parity evidence.

After deployment, confirm the database container ID is unchanged and it remains healthy. Confirm the lexical dataset mount is still read-only. Do not use production learner records as test fixtures.

## Controlled app restart / recovery

The Compose restart policy for both services is `unless-stopped`; this is configured to restart services after Docker daemon/host restart. Do not reboot the host for this milestone; no host reboot is needed to validate app recovery.

With the database confirmed healthy, restart only the app and repeat the bounded health, endpoint, source-parity, and database-identity checks:

```bash
set -euo pipefail
DB_ID_BEFORE="$(docker compose --env-file "$ENV_FILE" -p vocab-app ps -q vocab-db)"
docker compose --env-file "$ENV_FILE" -p vocab-app restart vocab-app
```

Use the health-check procedure above. Then confirm the `vocab-db` container ID still equals `DB_ID_BEFORE` and its health is `healthy`. A failed app restart is not permission to restart or recreate PostgreSQL.

## Browser smoke

At `http://192.168.1.173:8501/`, verify that the learner page loads, search a representative word (for example, `make`), confirm the result renders and the installed dataset identity is visible, and observe no obvious runtime error. This is a deployment smoke check, not the full lexical acceptance corpus. Do not use 8502/8503/8504 as proof for the canonical service.

## Private Tailscale Serve access

The approved mobile access is Tailscale Serve, which is tailnet-only. Funnel, public reverse proxies, router forwarding, wildcard `0.0.0.0:8501` binds, and exit-node configuration are not part of this setup. Tailnet ACLs and device access policies continue to govern access.

Confirm the app's local health endpoint works before configuring Serve:

```bash
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8501/_stcore/health
tailscale serve status
tailscale funnel status
```

Inspect the existing Serve configuration before changing or disabling anything. If there is no conflicting Serve configuration and Tailscale HTTPS/Serve has already been enabled for the tailnet by the Product Owner, configure the persistent proxy:

```bash
tailscale serve --bg 8501
tailscale serve status
tailscale funnel status
```

`--bg` stores the Serve configuration in the Tailscale daemon for persistence across daemon restarts. Confirm status reports the exact `https://<server>.<tailnet>.ts.net` URL, marks it `(tailnet only)`, and shows proxy `http://127.0.0.1:8501`. `tailscale funnel status` must not report a public Funnel listener. If Serve is not enabled and the CLI asks for admin consent, stop and request the Product Owner to complete that action; do not capture or include consent URLs/tokens in documentation or logs. If Tailscale warns that the DNS name will appear in certificate-transparency logs, record the warning but do not treat that name visibility as public application access.

Test the HTTPS URL from a separate authenticated tailnet client. A same-host request to its own Tailscale address may not be a valid proxy/TLS test. Confirm the Vocab page loads, `make` lookup renders, the dataset identity is visible, and there is no obvious Streamlit/WebSocket proxy error. The physical iPhone acceptance remains required: use the same exact Serve URL on home Wi-Fi and cellular with Tailscale enabled, then disable Tailscale and verify the URL cannot be reached; re-enable Tailscale after the privacy check. Do not claim these checks based only on Serve status or a host-local health check.

To disable Vocab Serve, first inspect both status commands and confirm the active Serve configuration is only the Vocab proxy. Then use the installed CLI's Serve reset operation and verify the result:

```bash
tailscale serve status
tailscale funnel status
tailscale serve reset
tailscale serve status
tailscale funnel status
```

`tailscale serve reset` clears this node's Serve configuration; do not use it if any unrelated Serve service is present. It does not disable Tailscale, remove the node from the tailnet, or roll back the database. After disabling Serve, verify that the LAN endpoint still works and that the tailnet HTTPS URL is no longer served.

## Rollback boundary

If the new app fails learner smoke acceptance and the recorded image is known to correspond to a Product-Owner-accepted source revision, restore its saved image tag and recreate only the app:

```bash
set -euo pipefail
docker image tag "$ROLLBACK_TAG" vocab-app-vocab-app:latest
docker compose --env-file "$ENV_FILE" -p vocab-app \
  up -d --no-build --no-deps --force-recreate vocab-app
```

Alternatively, use a clean checkout of the Product-Owner-selected accepted revision and build only `vocab-app`. Re-run health and browser smoke checks. Compare container files against the source revision associated with the rollback image, not against a different currently checked-out revision.

Rollback is application-source/image rollback only. It does not authorize Git history mutation by the Coder, PostgreSQL/schema rollback, learner-record changes, or dataset changes. Database rollback is not automatic or authorized by this runbook. Stop if restoring the app would require a destructive data action or an unapproved revision.

## Recorded deployment checks

For each deployment, retain non-secret evidence of the accepted Git revision, Compose project and service identities, app/database container identities before and after, image ID, env-file permission/presence checks, health transition, endpoint result, per-file source parity, browser smoke, and any restart check. Never include the environment file contents or credential values.
