#!/usr/bin/env python3
"""Build a review/test artifact, not a production release. No credentials needed."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from labbootstrap.common import source_digest, source_files


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    digest = source_digest(ROOT)
    prefix = 'lab-bootstrap-candidate-' + digest[:12]
    archive = output / (prefix + '.tar.gz')
    files = {name: path.read_bytes() for name, path in source_files(ROOT)}
    for name in ('README.md', 'CHANGELOG.md', 'bootstrap.sh', 'docs/AUDIT.md',
                 'docs/DESIGN.md', 'docs/VERIFICATION.md', 'docs/CHECKPOINT.md',
                 'docs/VM-ACCEPTANCE.md', 'docs/RECOVERY.md', 'docs/SECURITY-REVIEW.md',
                 'docs/evidence/vm-43651778256.json'):
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError('Artifact refuses symlink/out-of-tree documentation')
        files[name] = path.read_bytes()
    files['CANDIDATE.json'] = (json.dumps({
        'source_digest': digest, 'production_ready': False,
        'target': 'Ubuntu 22.04 amd64',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }, sort_keys=True, indent=2) + '\n').encode()
    # Refuse overwrites: artifacts from another build may be owner work.
    with archive.open('xb') as stream:
        with gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as tar:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(prefix + '/' + name)
                    info.size = len(data)
                    info.mode = 0o755 if name in ('install.sh', 'bootstrap.sh') else 0o644
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(data))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_suffix('.gz.sha256').open('x') as stream:
        stream.write(checksum + '  ' + archive.name + '\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    print(build(parser.parse_args().output))
