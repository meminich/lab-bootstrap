"""Pinned, isolated controller runtime. Never replace Ubuntu's Python."""
import hashlib
import io
from pathlib import Path
import os
import tempfile
import urllib.request
import zipfile

from labbootstrap.common import SafetyError, load_json, run


def prepare(root, install_dir):
    toolchain = load_json(root / 'toolchain.json')
    uv = install_dir / 'uv'
    environment = {
        'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8',
        'UV_PYTHON_INSTALL_DIR': str(install_dir / 'python'),
        'UV_CACHE_DIR': str(install_dir / 'cache'),
        'UV_PYTHON_BIN_DIR': str(install_dir / 'bin'),
    }
    if uv.is_symlink():
        raise SafetyError('Path uv tidak boleh berupa symlink.')
    if not uv.exists():
        with urllib.request.urlopen(toolchain['uv']['url'], timeout=120) as response:
            wheel = response.read(80 * 1024 * 1024)
        if hashlib.sha256(wheel).hexdigest() != toolchain['uv']['sha256']:
            raise SafetyError('Checksum uv tidak cocok; unduhan tidak dijalankan.')
        archive = zipfile.ZipFile(io.BytesIO(wheel))
        member = next(name for name in archive.namelist() if name.endswith('.data/scripts/uv'))
        # Extract only the binary, not arbitrary paths from the archive.
        binary = archive.read(member)
        if hashlib.sha256(binary).hexdigest() != toolchain['uv']['binary_sha256']:
            raise SafetyError('Checksum binary uv tidak cocok.')
        fd, temporary = tempfile.mkstemp(prefix='.uv-', dir=install_dir)
        try:
            os.fchmod(fd, 0o700)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(binary)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, uv)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if hashlib.sha256(uv.read_bytes()).hexdigest() != toolchain['uv']['binary_sha256']:
        raise SafetyError('Binary tooling existing berubah; tidak dijalankan.')
    # Check the pinned binary version; source/state ownership is checked by caller.
    result = run([str(uv), '--version'], env=environment, capture_output=True)
    if result.stdout.split()[:2] != ['uv', toolchain['uv']['version']]:
        raise SafetyError('Versi tooling existing berbeda. Jangan update otomatis.')
    run([str(uv), '--no-config', 'python', 'install', toolchain['python'],
         '--no-bin'], env=environment)
    venv = install_dir / 'venv'
    if venv.is_symlink():
        raise SafetyError('Path virtualenv tidak boleh berupa symlink.')
    if not (venv / 'bin/python').exists():
        run([str(uv), '--no-config', 'venv', '--managed-python', '--no-project', '--allow-existing',
             '--python', toolchain['python'], str(venv)], env=environment)
    run([str(uv), '--no-config', 'pip', 'sync', '--python', str(venv / 'bin/python'),
         '--require-hashes', '--only-binary', ':all:', '--index-url',
         'https://pypi.org/simple', str(root / 'requirements.lock')], env=environment)
    return venv / 'bin/ansible-playbook'
