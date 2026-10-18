"""Create local credentials for the optional password-protected remote entry."""
import argparse
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = 'caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f'


def setup(directory: Path, username: str = 'owner') -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', username):
        raise ValueError('Username must contain 1-32 letters, numbers, underscores or hyphens')
    directory.mkdir(parents=True, exist_ok=True)
    env_path = directory / '.env'
    credentials_path = directory / '.credentials.json'
    if env_path.exists() or credentials_path.exists():
        if not (env_path.exists() and credentials_path.exists()):
            raise RuntimeError('Incomplete existing remote configuration; preserve it and inspect locally')
        return {'created': False, 'credentialsFile': str(credentials_path)}
    password = secrets.token_urlsafe(24)
    result = subprocess.run(
        ['docker', 'run', '--rm', '-i', CADDY_IMAGE, 'caddy', 'hash-password'],
        # Binary stdin avoids Windows converting LF to CRLF before hashing.
        input=(password + '\n').encode('utf-8'), capture_output=True, timeout=60,
    )
    match = re.search(r'\$2[aby]\$\d{2}\$[A-Za-z0-9./]{53}', result.stdout.decode('utf-8'))
    if result.returncode or not match:
        raise RuntimeError('Could not generate a password hash; no remote credentials were written')
    # Single quotes prevent Compose from interpreting the bcrypt dollar signs.
    env_path.write_text(f"REMOTE_AUTH_USER={username}\nREMOTE_AUTH_HASH='{match.group(0)}'\n", encoding='utf-8')
    credentials_path.write_text(json.dumps({'username': username, 'password': password}, indent=2), encoding='utf-8')
    for path in (env_path, credentials_path):
        path.chmod(0o600)
    if os.name == 'nt':
        identity = subprocess.run(['whoami'], capture_output=True, text=True, check=True).stdout.strip()
        for path in (env_path, credentials_path):
            subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                            f'{identity}:(F)', 'SYSTEM:(F)'], capture_output=True, check=True)
    return {'created': True, 'username': username, 'credentialsFile': str(credentials_path)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'infrastructure/remote-access')
    parser.add_argument('--username', default='owner')
    args = parser.parse_args()
    print(json.dumps(setup(args.directory, args.username)))
