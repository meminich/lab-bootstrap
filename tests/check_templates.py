"""Run with the pinned controller Python. Does not run an Ansible apply."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]


class TemplateChecks(unittest.TestCase):
    def setUp(self):
        self.environment = Environment(loader=FileSystemLoader(ROOT / 'templates/workspace'),
                                       undefined=StrictUndefined, keep_trailing_newline=True)
        self.values = {'hostname': 'vpslab', 'timezone': 'Asia/Jakarta', 'tailscale_ip': '100.100.0.2'}

    def render(self, name):
        return self.environment.get_template(name).render(**self.values)

    def test_all_workspace_templates_render(self):
        for path in (ROOT / 'templates/workspace').glob('*.j2'):
            with self.subTest(name=path.name):
                self.assertTrue(self.render(path.name).strip())

    def test_compose_requires_explicit_ip_and_has_no_shared_container_name(self):
        compose = yaml.safe_load(self.render('compose.yml.j2'))
        app = compose['services']['app']
        self.assertNotIn('container_name', app)
        self.assertIn('${TAILSCALE_IP:?', app['ports'][0])
        self.assertNotIn('network_mode', app)
        self.assertTrue(app['volumes'][0].endswith(':ro'))

    @unittest.skipUnless(shutil.which('docker'), 'Docker CLI optional; no socket is used')
    def test_real_compose_config_is_local_and_does_not_start_containers(self):
        with tempfile.TemporaryDirectory(prefix='lab-compose-check-') as temporary:
            directory = Path(temporary)
            compose = directory / 'compose.yaml'
            env = directory / '.env.example'
            compose.write_text(self.render('compose.yml.j2'))
            env.write_text(self.render('env.j2'))
            docker_env = {**os.environ, 'DOCKER_CONFIG': str(directory / 'docker-config'),
                          'DOCKER_HOST': 'unix://' + str(directory / 'no-daemon.sock')}
            result = subprocess.run(['docker', 'compose', '--env-file', str(env),
                                     '-f', str(compose), 'config', '--quiet'],
                                    cwd=directory, env=docker_env, capture_output=True, text=True, check=False)
            if 'not a docker command' in result.stderr or 'unknown flag: --env-file' in result.stderr:
                self.skipTest('Compose plugin not available')
            self.assertEqual(result.returncode, 0, result.stderr)
            env.write_text('PORT=8080\nTZ=Asia/Jakarta\n')
            result = subprocess.run(['docker', 'compose', '--env-file', str(env),
                                     '-f', str(compose), 'config', '--quiet'],
                                    cwd=directory, env=docker_env, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0, 'Missing bind IP must fail closed')

    def test_all_playbooks_are_yaml_and_have_no_shell_tasks(self):
        for path in (ROOT / 'playbooks').glob('*.yml'):
            with self.subTest(name=path.name):
                plays = yaml.safe_load(path.read_text())
                self.assertIsInstance(plays, list)
                self.assertNotIn('ansible.builtin.shell', path.read_text())
                self.assertNotIn('chown -R', path.read_text())
                self.assertNotIn('ufw reset', path.read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
