# Publishing a Sedrava site from GitHub to a VDS (template)

This workflow is an **opt-in template**, not an active production deployment. It is based on the experimental Web UI 0.11 branch. It builds the real `.sdr` source and always uploads a preview artifact. The default manual action (`publish=false`) cannot connect to a server.

## Setup

1. Choose a **dedicated preview domain** and an **empty document root** on the VDS. Do not point this at the current sedrava-site or another existing website.
2. Configure a restricted SSH deployment user on the VDS, with write permission **only** to that preview root. Use a dedicated Ed25519 key. Do not commit the private key.
3. In repository Actions secrets configure `SEDRAVA_DEPLOY_SSH_KEY`, `SEDRAVA_DEPLOY_HOST`, `SEDRAVA_DEPLOY_USER`, `SEDRAVA_DEPLOY_KNOWN_HOSTS` (the server host-key entry verified through a trusted channel). In Actions variables configure `SEDRAVA_DEPLOY_PATH` (absolute path under `/srv/www/` or `/var/www/`) and optional `SEDRAVA_DEPLOY_SSH_PORT` (default 22).
4. Run **Sedrava site build and optional VDS deploy** manually with `publish=false`. Download the preview artifact and inspect it.
5. Only after confirming the target path is an isolated site directory, manually run with `publish=true`. The deploy uses rsync `--delete` and will remove files in the destination that are absent from the build. Never target a shared directory.
6. Set Nginx/FastPanel document root to that preview directory, configure HTTPS, and test the page and assets.

## Planned improvements before automatic production deployment

- Separate preview and production environments with restricted branches and required approval.
- Stage each build into a versioned release directory on the server, then atomically switch the live symlink; retain previous releases for rollback.
- Add smoke tests against the published URL and automatic rollback on failure.
- Pin site compiler version to a released Web UI version after 0.11 integration; currently this workflow uses the branch source.
- Replace the sample `examples/web_ui_011_landing.sdr` with the chosen actual site source.
- Add `push` triggers for preview only after the above protections are verified.

No credentials, hostnames, paths or production deploy settings have been configured.
