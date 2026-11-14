"""Unprivileged regression tests. Never execute the body of the old installer."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")


class EntryPointSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lab-bootstrap-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.sentinel = self.work / "unsafe-command-called"
        # If sourced, this config writes the sentinel and terminates the installer.
        (self.work / "config.env").write_text(
            'printf unsafe > "$TEST_SENTINEL"\nexit 93\n', encoding="utf-8"
        )
        tools = self.work / "bin"
        tools.mkdir()
        for name in (
            "sudo", "id", "apt-get", "ufw", "systemctl", "tailscale", "docker",
            "curl", "tee", "touch", "mkdir", "chown", "sed", "python3",
        ):
            fake = tools / name
            fake.write_text(
                '#!/bin/sh\nprintf unsafe > "$TEST_SENTINEL"\nexit 94\n',
                encoding="utf-8",
            )
            fake.chmod(0o755)
        self.env = {
            "PATH": str(tools),
            "HOME": str(self.work),
            "TEST_SENTINEL": str(self.sentinel),
        }

    def run_script(self, *args, legacy=False, piped=False):
        script = ROOT / ("legacy/bootstrap.sh" if legacy else "bootstrap.sh")
        before = self.snapshot()
        result = subprocess.run(
            [BASH, "-s", "--", *args] if piped else [BASH, str(script), *args],
            input=script.read_text() if piped else "",
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertFalse(self.sentinel.exists(), result.stderr)
        self.assertEqual(before, self.snapshot(), "entry point wrote test workspace")
        return result

    def snapshot(self):
        return {
            str(p.relative_to(self.work)): (
                p.stat().st_mode,
                p.read_bytes() if p.is_file() else None,
            )
            for p in self.work.rglob("*")
        }

    def test_help_succeeds_without_tools_or_config(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("BELUM tersedia", result.stdout)

    def test_short_help(self):
        self.assertEqual(self.run_script("-h").returncode, 0)

    def test_plan_is_explicitly_not_an_ansible_simulation(self):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("BUKAN simulasi", result.stdout)
        self.assertIn("22.04", result.stdout)

    def test_no_arguments_refuses_installation(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("STOP", result.stderr)

    def test_legacy_flags_cannot_bypass_guard(self):
        for args in (
            ("--yes",), ("--skip-verify",), ("--force",),
            ("--only", "50"), ("--from", "30"), ("--unknown",),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_script(*args).returncode, 0)

    def test_extra_arguments_refused(self):
        for args in (("--dry-run", "--yes"), ("--help", "--force")):
            with self.subTest(args=args):
                self.assertEqual(self.run_script(*args).returncode, 2)

    def test_pipe_input_cannot_install(self):
        self.assertEqual(self.run_script(piped=True).returncode, 1)

    def test_pipe_input_can_print_plan(self):
        self.assertEqual(self.run_script("--dry-run", piped=True).returncode, 0)

    def test_archive_refuses_all_execution_modes(self):
        for args in ((), ("--dry-run",), ("--yes", "--skip-verify")):
            with self.subTest(args=args):
                result = self.run_script(*args, legacy=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("dinonaktifkan", result.stderr)

    def test_archive_pipe_is_also_blocked(self):
        self.assertEqual(self.run_script(legacy=True, piped=True).returncode, 1)

    def test_shell_syntax(self):
        for path in ("bootstrap.sh", "legacy/bootstrap.sh"):
            with self.subTest(path=path):
                result = subprocess.run(
                    [BASH, "-n", str(ROOT / path)], capture_output=True, text=True,
                    timeout=5, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


class DocumentationContract(unittest.TestCase):
    def text(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_readme_does_not_offer_live_installer(self):
        readme = self.text("README.md")
        self.assertIn("BELUM SIAP UNTUK INSTALASI", readme)
        self.assertIn("22.04 LTS", readme)
        self.assertNotIn("raw.githubusercontent.com", readme)
        self.assertNotIn("curl -fsSL", readme)

    def test_readme_relative_links_resolve(self):
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", self.text("README.md")):
            if "://" not in target:
                self.assertTrue((ROOT / target).is_file(), target)

    def test_templates_are_not_host_status_reports(self):
        host = self.text("templates/home/AGENTS.md")
        self.assertIn("Template", host)
        self.assertIn("belum", host.lower())
        for stale_claim in (
            "cloud-init dimatikan", "Tailscale SSH aktif", "Swap aktif",
            "tanpa auto-restart", "100.123.138.28", "100.64.0.1",
        ):
            with self.subTest(claim=stale_claim):
                self.assertNotIn(stale_claim, host)

    def test_rules_require_authorization_and_explicit_binding(self):
        host = self.text("templates/home/AGENTS.md")
        self.assertIn("bukan izin", host)
        self.assertIn("${TAILSCALE_IP:?wajib diisi}", host)
        self.assertIn("setara root", host)
        self.assertIn("IPv6", host)
        self.assertIn("konfirmasi", host)
        self.assertIn("symlink existing", host)

    def test_workspace_points_to_canonical_rules_and_registry(self):
        workspace = self.text("templates/playground/AGENTS.md")
        self.assertIn("../AGENTS.md", workspace)
        self.assertIn("portal/labs.json", workspace)
        self.assertIn("Discovery bukan otorisasi", workspace)

    def test_no_secret_config_examples(self):
        config = self.text("config.env.example")
        self.assertNotIn("ADMIN_PASSWORD=", config)
        self.assertNotIn("TAILSCALE_AUTHKEY=", config)
        self.assertIn("LEGACY REFERENCE ONLY", config)

    def test_repo_rules_are_separate_from_host_template(self):
        rules = self.text("AGENTS.md")
        self.assertIn("source repo", rules)
        self.assertIn("bukan aturan operasional VPS", rules)
        self.assertIn("Jangan menghapus guard", rules)

    def test_design_requires_access_gate_and_release_evidence(self):
        design = self.text("docs/DESIGN.md")
        verification = self.text("docs/VERIFICATION.md")
        self.assertIn("belum diimplementasikan", design)
        self.assertIn("--yes", design)
        self.assertIn("root-owned", design)
        self.assertIn("belum diuji", verification)
        self.assertIn("bukan rilis installer", verification)


if __name__ == "__main__":
    unittest.main()
