# Versions and updates

## Versions

The app follows [Semantic Versioning](https://semver.org) (`MAJOR.MINOR.PATCH`). The installed version is shown in the left menu, in **Settings → Version & updates**, in `GET /api/version` and in the Docker image tags. Every release has a section in [CHANGELOG.md](../CHANGELOG.md); the same text is the body of the [GitHub release](https://github.com/blitzu/teslamate-ui/releases) and is shown in the app under *What changed*.

## Being told about new versions

Twice a day the server asks GitHub (`api.github.com/repos/<owner>/<repo>/releases/latest`, one anonymous request, nothing about you or your car is sent) which release is the latest.

* When it is newer than yours, the left menu shows *new vX.Y.Z*, the dashboard shows a chip (administrators only), **Settings → Version & updates** shows the release notes, and — once per version — your notification webhook receives *"New version vX.Y.Z"* (toggle: **Notifications → New app version**).
* Switch the check off in Settings (or `UPDATE_CHECK=0`). A build whose version ends in `-private` never checks. Forks can point the check at their own repository with `UPDATE_REPO=owner/name`.

## Updating

**Published images (recommended).** Each release publishes multi-architecture images (`linux/amd64`, `linux/arm64`) to `ghcr.io/blitzu/teslamate-ui` and `…-proxy`:

```bash
docker compose pull && docker compose up -d
```

Pin a version with `APP_TAG=1.0.0` in `.env` (default `latest`); roll back by setting the previous tag and running `docker compose up -d`. The files in `data/` stay compatible and each keeps a `*.bak`.

**From source.** `git pull && docker compose up -d --build`.

## Built-in updater (no Watchtower)

A tiny optional container, `updater`, gives the **Update now** button (and optional daily automatic updates) without any third-party tool. It exposes no port to the host: the app reaches it over the compose network. It only ever runs `docker compose pull` and `docker compose up -d` for the services in `UPDATER_SERVICES` (default `ui proxy`), after checking a bearer token, one run at a time.

Set it up once, in `.env` (generate the token with `openssl rand -hex 16`):

```bash
UPDATER_TOKEN=<16+ random characters>
PROJECT_DIR=/absolute/path/of/this/folder     # setup.sh writes it for new installs; check with `pwd`
UPDATE_WEBHOOK=http://updater:8080/update
UPDATE_TOKEN=<the same token>
# UPDATER_AUTO_HOURS=24                          # optional: also update by itself once a day
```

```bash
docker compose --profile updater up -d updater
```

Then **Settings → Version & updates** shows the **Update now** button when a new version exists; pressing it pulls the new images and restarts the app (about a minute). `GET http://updater:8080/status` (same token) shows the log of the last run.

**What you should know**

* It mounts the Docker socket, which is root-equivalent on the host. That is unavoidable for any updater (Watchtower does the same); this one is a single small file you can read ([`updater/updater.py`](../updater/updater.py)) and it only acts on the services you name. Do not publish its port and keep the token secret.
* For installs from published images (`docker compose pull`). If you build from source, update with `git pull && docker compose up -d --build`.
* The project folder is mounted **at the same path as on the host**, because compose resolves `./data`, `./fleet` and the env files relative to it; that is why `PROJECT_DIR` must be the real absolute path.
* The updater itself is not restarted by its own run; update it from the host when a release changes it: `docker compose --profile updater pull updater && docker compose --profile updater up -d updater`.
* Rolling back: set `APP_TAG=<previous version>` in `.env` and press the button (or run `docker compose up -d`).

## Automatic updates

The app has no access to Docker (on purpose: it never mounts the Docker socket and cannot replace its own container), so automatic updates are done by a small updater that watches the images. [Watchtower](https://containrrr.dev/watchtower/) example, added to your `docker-compose.yml`:

```yaml
  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes: ["/var/run/docker.sock:/var/run/docker.sock"]
    environment:
      WATCHTOWER_LABEL_ENABLE: "true"        # only containers labelled com.centurylinklabs.watchtower.enable (ui and proxy are)
      WATCHTOWER_CLEANUP: "true"
      WATCHTOWER_POLL_INTERVAL: "86400"      # check once a day
      WATCHTOWER_HTTP_API_UPDATE: "true"     # for the "Update now" button
      WATCHTOWER_HTTP_API_PERIODIC_POLLS: "true"
      WATCHTOWER_HTTP_API_TOKEN: "a-long-random-token"
```

Already running Watchtower (or another updater)? Just keep the two labels the provided `docker-compose.yml` sets on `ui` and `proxy`.

**"Update now" button.** In *Settings → Version & updates* enter the updater address (for Watchtower: `http://watchtower:8080/v1/update`, the two containers must share a Docker network) and its token. When a new version is available an **Update now** button appears; it calls the updater, which pulls the new images and restarts the containers (about a minute). Changing the address later asks for the token again.

## For maintainers: making a release

1. Put the new number in `VERSION` and add a `## X.Y.Z - YYYY-MM-DD` section at the top of `CHANGELOG.md` (the text under it becomes the release notes).
2. Commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The *Release* workflow checks that the tag matches `VERSION` and `CHANGELOG.md`, runs the tests, publishes the images to GHCR and creates the GitHub release. The first time, make the two packages public (GitHub → your profile → Packages → package settings → *Change visibility*) so that others can pull them without logging in.
