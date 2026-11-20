"""Recover public hashed assets from explicitly selected local frontend images."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+')
    args=parser.parse_args()
    if not all(re.fullmatch(r'(?:sha256:)?[0-9a-f]{12,64}',image) for image in args.images):
        parser.error('Use immutable local image IDs only.')
    subprocess.run(['docker','volume','inspect','--format','{{.Name}}','ai-quant_frontend-assets'],check=True,capture_output=True)
    script=(ROOT/'frontend/archive-assets.sh').read_bytes().replace(b'\r\n',b'\n')
    subprocess.run(['docker','exec','-i','ai-quant-frontend-1','sh','-s'],input=script,check=True)
    for image in args.images:
        subprocess.run(['docker','run','--pull=never','--rm','-i','--network','none','--read-only','--user','101:101',
            '--mount','type=volume,source=ai-quant_frontend-assets,target=/var/lib/nginx/asset-archive',
            '--entrypoint','sh',image,'-s'],input=script,check=True)
    print(f'Archived public assets from {len(args.images)} local frontend images; existing files preserved.')

if __name__=='__main__':main()
