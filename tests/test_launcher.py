"""Launcher tests: no real network, privileged tools or host mutation."""

import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab_launcher', ROOT / 'setup.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_safe_entrypoints(self):
        for option in ('--help', '--dry-run'):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'setup.py'), option],
                                        cwd=directory, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_arguments_rejected(self):
        result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'setup.py'), '--yes'],
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_non_root_and_noninteractive_are_rejected(self):
        with patch.object(launcher.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(ValueError, 'root'):
                launcher.check_host()
        with patch.object(launcher.os, 'geteuid', return_value=0), \
                patch.object(launcher.sys.stdin, 'isatty', return_value=False):
            with self.assertRaisesRegex(ValueError, 'terminal interaktif'):
                launcher.check_host()

    def test_defaults_and_invalid_config_retry(self):
        # This fixture uses the same validation module as the verified release.
        with patch('builtins.input', side_effect=['root', '', '', '', '', '', '', '']), \
                contextlib.redirect_stdout(io.StringIO()):
            config = launcher.ask_config(ROOT)
        self.assertEqual(config, {'admin_user': 'vpsadmin', 'hostname': 'vpslab',
                                  'timezone': 'Asia/Jakarta', 'swap_gib': 4})

    def response(self, data, url='https://release-assets.githubusercontent.com/example'):
        response = io.BytesIO(data)
        response.geturl = lambda: url
        return response

    def test_download_verifies_pinned_digest(self):
        data = b'verified archive fixture'
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'bundle'
            with patch.object(launcher.urllib.request, 'urlopen', return_value=self.response(data)), \
                    patch.object(launcher, 'SHA256', hashlib.sha256(data).hexdigest()):
                launcher.download(destination)
            self.assertEqual(destination.read_bytes(), data)

    def test_download_rejects_corruption_size_and_http(self):
        cases = ({}, {'MAX_ARCHIVE': 1}, {})
        urls = ('https://example.com/file', 'https://example.com/file', 'http://example.com/file')
        for overrides, url in zip(cases, urls):
            with self.subTest(url=url, overrides=overrides), tempfile.TemporaryDirectory() as directory:
                with patch.object(launcher.urllib.request, 'urlopen',
                                  return_value=self.response(b'bad', url)), \
                        contextlib.ExitStack() as stack:
                    for key, value in overrides.items():
                        stack.enter_context(patch.object(launcher, key, value))
                    with self.assertRaises(ValueError):
                        launcher.download(Path(directory) / 'bundle')

    def make_bundle(self, directory, entries):
        archive = Path(directory) / 'fixture.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, content, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(content) if kind == tarfile.REGTYPE else 0
                info.linkname = '/etc/passwd' if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ''
                bundle.addfile(info, io.BytesIO(content) if info.isfile() else None)
        return archive

    def entries(self):
        prefix = launcher.ARCHIVE.removesuffix('.tar.gz')
        return [(prefix + '/' + name, b'fixture', tarfile.REGTYPE) for name in
                ('install.sh', 'labbootstrap/installer.py', 'labbootstrap/common.py')]

    def test_unpack_valid_regular_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = launcher.unpack(self.make_bundle(directory, self.entries()), Path(directory) / 'out')
            self.assertEqual((root / 'install.sh').read_bytes(), b'fixture')
            self.assertEqual((root / 'install.sh').stat().st_mode & 0o777, 0o600)

    def test_unpack_rejects_unsafe_entries_before_writing(self):
        prefix = launcher.ARCHIVE.removesuffix('.tar.gz')
        for name, kind in (('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                           (prefix + '/../../escape', tarfile.REGTYPE),
                           ('other/install.sh', tarfile.REGTYPE),
                           (prefix + '/link', tarfile.SYMTYPE),
                           (prefix + '/hardlink', tarfile.LNKTYPE),
                           (prefix + '/fifo', tarfile.FIFOTYPE),
                           (prefix + '/install.sh', tarfile.REGTYPE)):
            with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as directory:
                archive = self.make_bundle(directory, self.entries() + [(name, b'x', kind)])
                destination = Path(directory) / 'out'
                with self.assertRaises(ValueError):
                    launcher.unpack(archive, destination)
                self.assertFalse(destination.exists())

    def test_unpack_rejects_size_and_missing_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.make_bundle(directory, self.entries())
            with patch.object(launcher, 'MAX_UNPACKED', 1), self.assertRaises(ValueError):
                launcher.unpack(archive, Path(directory) / 'oversize')
            archive = self.make_bundle(directory, self.entries()[:1])
            with self.assertRaisesRegex(ValueError, 'tidak lengkap'):
                launcher.unpack(archive, Path(directory) / 'incomplete')

    def test_preflight_failure_never_downloads(self):
        with patch.object(sys, 'argv', ['setup.py']), \
                patch.object(launcher, 'check_host', side_effect=ValueError('not fresh')), \
                patch.object(launcher, 'download') as download:
            with self.assertRaises(ValueError):
                launcher.main()
            download.assert_not_called()

    def test_decline_never_downloads_or_creates_directory(self):
        with patch.object(sys, 'argv', ['setup.py']), patch.object(launcher, 'check_host'), \
                patch('builtins.input', return_value='n'), \
                patch.object(launcher.tempfile, 'mkdtemp') as mkdir, \
                patch.object(launcher, 'download') as download, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(), 0)
            mkdir.assert_not_called()
            download.assert_not_called()

    def test_verified_wizard_handoff_preserves_guards_and_exit_status(self):
        config = {'admin_user': 'vpsadmin', 'hostname': 'vpslab',
                  'timezone': 'Asia/Jakarta', 'swap_gib': 4}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'verified'
            with patch.object(sys, 'argv', ['setup.py']), patch.object(launcher, 'check_host'), \
                    patch('builtins.input', return_value='y'), \
                    patch.object(launcher.tempfile, 'mkdtemp', return_value=directory), \
                    patch.object(launcher, 'download'), patch.object(launcher, 'unpack', return_value=root), \
                    patch.object(launcher, 'ask_config', return_value=config), \
                    patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run, \
                    patch.object(launcher.os, 'umask'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.main(), 7)
                args = run.call_args.args[0]
                self.assertEqual(args[:4], ['/bin/bash', str(root / 'install.sh'), '--apply', '--experimental'])
                self.assertEqual(args[4:], ['--config', str(Path(directory) / 'config.json')])

    def test_corrupt_download_never_runs_installer(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'argv', ['setup.py']), patch.object(launcher, 'check_host'), \
                    patch('builtins.input', return_value='y'), \
                    patch.object(launcher.tempfile, 'mkdtemp', return_value=directory), \
                    patch.object(launcher, 'download', side_effect=ValueError('checksum')), \
                    patch.object(launcher.subprocess, 'run') as run, \
                    patch.object(launcher.os, 'umask'), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    launcher.main()
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
