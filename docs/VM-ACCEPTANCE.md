# Unattended fresh-VM acceptance

Status: harness implemented; results must come from a completed GitHub run, not
from the existence of these scripts. No production Tailscale credentials required.

## Isolation

- Runs only on a disposable standard GitHub-hosted Ubuntu runner. Host launcher
  refuses normal execution outside `GITHUB_ACTIONS=true`; do not spoof that flag
  on the live VPS.
- Two genuine Ubuntu 22.04 kernels run under QEMU, KVM where available and TCG
  otherwise. Nested KVM is not guaranteed by GitHub; acceleration is recorded.
- Docker is only a wrapper for QEMU/tools and a temporary Headscale control plane.
  It is **not** used to impersonate a fresh systemd host. No privileged container,
  host networking, Docker socket mount, or published host port.
- The two guests have a virtual Ethernet link over a QEMU loopback socket. Its
  IPv4 benchmark subnet and IPv6 ULA model the non-tailnet/public side. SSH factory
  forwards bind only to container loopback, not the runner's public interface.
- The control server is HTTPS with a generated fixture CA, fake identity, and
  short-lived single-use auth keys. Private DERP only, no production tailnet.
- Fixture allocation uses `100.64.0.0/28`. Headscale v0.29.7's
  `GenerateIPv4DNSRootDomain` expands `/24` into 256 reverse-DNS routes, exceeding
  Jammy systemd-resolved's per-link domain limit and preventing short-name DNS.
  `/28` produces 16 routes, while retaining genuine MagicDNS and both IP families.
  No hosts-file entries, manual search-domain injection, or IP fallback is used.
- Only generated test artifacts are shared between fixture components. No lab
  service folders, credentials, runtime DBs, or user documents are mounted/read.
- Only sanitized reports/logs are uploaded. Never upload cloud-init seeds, disks,
  CA/private SSH keys, credentials, Headscale DB/state, or the whole work directory.
- Resources have unique names and are removed explicitly; no global prune or
  wildcard removal. The runner itself is disposable, including after cancellation.

## Test path

1. Verify the SHA256-pinned official Ubuntu cloud image; boot two fresh overlays.
2. Use only generated fixture root SSH keys to establish factory access.
3. Stage the **unchanged** candidate payload and run its real interactive installer.
4. At its ordinary password/login pause, register the target in the private
   Headscale network. No production `--auth-key`/`--skip-verify` option is added.
5. Deliberately fail the first access checkpoint and prove factory access remains.
6. Resume the same installed source. Three separate actual client SSH sessions
   enter the real sudo password and invoke the production verifier. No fabricated
   receipt, environment-based verifier bypass, or NOPASSWD policy.
   Each session opens an interactive login shell before typing sudo, matching
   the documented human workflow; remote-command SSH on the tested Tailscale/
   Jammy combination exposed a PTY without sudo's controlling terminal.
7. Prove non-tailnet IPv4/IPv6 SSH is blocked. Deploy the generated demo container;
   prove HTTP through the mesh and no exposure on the non-tailnet interfaces.
8. Create owned SQLite/document fixtures containing legacy placeholders. Rerun
   with a running container and verify hashes, inodes, UID/GID remain unchanged.
9. Reboot the actual target kernel; prove boot ID changes, SSH/DNS/Docker recover,
   non-tailnet exposure does not return, and data fixtures remain identical.

## Limits — not equivalent to the owner's account/provider

Headscale exercises real Tailscale daemons, transport, MagicDNS, and SSH policy,
but not commercial browser login, account ACLs, MFA/device approval, or the owner's
current tailnet configuration. Fixture enrollment covers the already-authenticated
node path after daemon installation. The first commercial browser login remains
an owner action at deployment time.

The Ubuntu image is official, not Contabo's exact image. The outside interface is
simulated, not Contabo public routing. Provider reinstall and recovery console
must not be marked tested by this harness. A passing fixture run alone must not
flip the candidate's `production_ready` field or publish a production release.

## References

- https://cloud-images.ubuntu.com/jammy/20261106/SHA256SUMS
- https://github.com/juanfont/headscale/releases/tag/v0.29.7
- https://github.com/juanfont/headscale/blob/v0.29.7/config-example.yaml
- https://github.com/juanfont/headscale/blob/v0.29.7/hscontrol/util/dns.go
- https://headscale.net/stable/ref/policy/
- https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
