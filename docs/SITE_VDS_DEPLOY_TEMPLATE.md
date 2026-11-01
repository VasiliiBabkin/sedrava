# Sedrava demo deployment to dev.virtreal.ru

Target URL: https://dev.virtreal.ru/ (DNS, TLS and availability must be checked on the server).
Target document root: `/var/www/virtreal_ru_usr27/data/www/virtreal.ru/dev`.

The workflow `.github/workflows/sedrava-site-vds.yml` compiles `examples/sedrava_public_showcase.sdr` using the experimental 0.11 compiler. It creates a downloadable preview artifact on every manual run. **No deployment occurs unless `publish=true` is selected.** The target path is fixed in the workflow, not controlled by an untrusted input.

## GitHub Actions configuration

Add these **repository secrets** (Settings → Secrets and variables → Actions):

- `SSH_HOST`: SSH server hostname or IP (not the web URL unless it resolves to the SSH server).
- `SSH_USER`: SSH account with write access to the target directory.
- `SSH_PRIVATE_KEY`: private Ed25519 key dedicated to this deployment. Never commit it.
- `SSH_KNOWN_HOSTS`: independently verified SSH host-key line (e.g. obtained from the VDS control panel or checked against a trusted server-side fingerprint).

Optional **repository variable**: `SSH_PORT` (default 22).

On the VDS, configure the website root to the exact directory above. The SSH user must be able to write there. The existing sedrava-site repository uses the same secret names, but GitHub repository secrets are scoped to their repository: configure them separately in sedrava or use authorized organization secrets. Do not copy private key material into commits or chat. The workflow uses the same tar-over-SSH transfer as sedrava-site and does not delete unrelated files; files with matching names may still be overwritten. Use a dedicated preview directory and check it before first deployment.

## First run

1. Open Actions → **Sedrava site build and optional VDS deploy** → Run workflow on `infra/site-deploy-template`.
2. Leave `publish=false` for the first build; download and inspect the `sedrava-site-preview` artifact.
3. Verify DNS, TLS, the document root and SSH credentials; check the directory is dedicated to this demo.
4. Rerun with `publish=true`. The workflow sends the built files by SSH/rsync.
5. Visit https://dev.virtreal.ru/ and verify the logo, CSS, navigation and mobile view.

This is a manual preview deployment, **not yet automatic push-to-production**. A later iteration can add branch-restricted automatic preview deployment, versioned directories, atomic cutover, health checks and rollback. It must be validated before being used for a production site.

The current branch and workflow are not merged into `main`. Workflow availability in GitHub Actions depends on GitHub's workflow_dispatch/default-branch rules; if the manual action is not visible, a separate approval and integration step is needed. No credentials are currently set by this PR.
