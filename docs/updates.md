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

## Built-in updater (nothing to configure)

From v1.4.0 the stack includes a tiny `updater` container. It gives you the **Update now** button in **Settings → Version & updates** with no settings at all:

1. A new version appears (the app checks GitHub twice a day, or press **Check now** any time).
2. **Settings → Version & updates** shows what changed. Press **Update now** and confirm.
3. The updater pulls the new images and restarts the app (about a minute). The page waits for the new version and reloads itself.

Nothing is updated unless you press the button (set `UPDATER_AUTO_HOURS=24` in `.env` if you *do* want a daily automatic update).

**If you are on an older version (before v1.4.0)** you need to do one manual update to get the updater: `git pull && docker compose up -d --build` (source install), or `docker compose pull && docker compose up -d` if you use the published images and have fetched the new `docker-compose.yml`. After that, every update is one click.

**How it works, and what you should know**

* It finds its own project folder and name from the labels compose puts on its container, creates a random token in `./data/updater.token` on first start (the app reads it from the same folder), and runs `docker compose pull` + `up -d` for the services `ui` and `proxy` only, in a short-lived helper container. Nothing to configure, no port published: the app reaches it over the compose network and it only accepts requests with the token.
* It needs the **Docker socket**, which is root-equivalent on the host. That is unavoidable for any updater (Watchtower does the same). The code is one small file you can read ([`updater/updater.py`](../updater/updater.py)). **If you prefer not to have it:** remove the `updater` block from `docker-compose.yml` (or run `docker compose rm -sf updater` and never start it) and update by hand; the app keeps telling you when a version is available.
* It replaces the app's images with the published ones (`docker compose pull`). If you changed the source locally, update with `git pull && docker compose up -d --build` instead. Changes to `docker-compose.yml` itself are not applied by the updater; when a release needs one, the CHANGELOG says so.
* Already using Watchtower or another updater? Whatever you set in Settings (or `UPDATE_WEBHOOK` / `UPDATE_TOKEN`) takes priority over the built-in one.
* Rolling back: set `APP_TAG=<previous version>` in `.env` and press **Update now** (or run `docker compose up -d`).
* `GET http://updater:8080/status` with the token (from `./data/updater.token`) shows the log of the last run; `docker logs tessie-updater` shows its start-up messages.

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
