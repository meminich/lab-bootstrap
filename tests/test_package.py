import hashlib
import json
from pathlib import Path
import tarfile
import subprocess
import tempfile
import unittest

from labbootstrap.common import source_digest
from scripts.build_candidate import build, ROOT


class CandidatePackageTests(unittest.TestCase):
    def test_unpacked_installer_plan_does_not_write_even_bytecode_or_load_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = build(directory / 'build')
            payload = directory / 'unpacked'
            with tarfile.open(archive, 'r:gz') as tar:
                for member in tar.getmembers():
                    self.assertTrue(member.isfile())
                    relative = member.name.split('/', 1)[1]
                    target = payload / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
            (payload / 'config.env').write_text('touch SHOULD_NOT_EXIST\n')
            before = {str(p.relative_to(payload)): p.read_bytes()
                      for p in payload.rglob('*') if p.is_file()}
            commands = [
                ['/bin/bash', str(payload / 'install.sh'), '--dry-run'],
                ['/usr/bin/python3', '-I', str(payload / 'labbootstrap/installer.py'), '--dry-run'],
            ]
            for command in commands:
                result = subprocess.run(command, cwd=payload, capture_output=True, text=True,
                                        env={'PATH': '/usr/bin:/bin', 'HOME': str(directory)},
                                        check=False, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('RENCANA SAJA', result.stdout)
                after = {str(p.relative_to(payload)): p.read_bytes()
                         for p in payload.rglob('*') if p.is_file()}
                self.assertEqual(before, after)
                self.assertFalse(any(p.name == '__pycache__' for p in payload.rglob('*')))

    def test_full_payload_roundtrip_and_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = build(Path(temporary))
            checksum = archive.with_suffix('.gz.sha256').read_text().split()[0]
            self.assertEqual(checksum, hashlib.sha256(archive.read_bytes()).hexdigest())
            with tarfile.open(archive, 'r:gz') as tar:
                contents = {}
                for member in tar.getmembers():
                    self.assertTrue(member.isfile())
                    self.assertNotIn('..', member.name.split('/'))
                    name = member.name.split('/', 1)[1]
                    contents[name] = tar.extractfile(member).read()
            manifest = json.loads(contents.pop('CANDIDATE.json'))
            self.assertFalse(manifest['production_ready'])
            self.assertEqual(manifest['source_digest'], source_digest(ROOT))
            self.assertEqual(set(contents), set(manifest['files']))
            for name, data in contents.items():
                self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['files'][name], name)
            for required in ('install.sh', 'labbootstrap/installer.py', 'playbooks/ansible.cfg',
                             'playbooks/prepare.yml', 'playbooks/lockdown.yml',
                             'playbooks/foundation.yml', 'requirements.lock'):
                self.assertIn(required, contents)
            self.assertFalse(any(name.startswith('legacy/') for name in contents))
            self.assertFalse(any(name.endswith('.env') for name in contents))

    def test_build_is_repeatable_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = build(Path(temporary) / 'first')
            second = build(Path(temporary) / 'second')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with self.assertRaises(FileExistsError):
                build(Path(temporary) / 'first')


if __name__ == '__main__':
    unittest.main()
