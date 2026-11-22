"""Build receipts and installed behavior checks for wheel and source artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]

def main():
    directory = Path(sys.argv[1]).resolve()
    profile = sys.argv[2] if len(sys.argv) > 2 else ''
    artifacts = sorted([*directory.glob('*.whl'), *directory.glob('*.tar.gz')])
    if len(artifacts) != 2:
        raise ValueError('Select exactly one wheel and one source distribution')
    receipts=[]
    for artifact in artifacts:
        with TemporaryDirectory() as temporary:
            outside = Path(temporary)
            environment = outside / 'env'
            subprocess.run(['uv', 'venv', str(environment), '--python', sys.executable], check=True)
            python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            target = str(artifact) + (f'[{profile}]' if profile else '')
            subprocess.run(['uv', 'pip', 'install', '--python', str(python), target], check=True, cwd=outside)
            subprocess.run([str(python), '-I', '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'], check=True, cwd=outside)
            subprocess.run(['uv', 'pip', 'check', '--python', str(python)], check=True, cwd=outside)
            probe = subprocess.run([str(python), '-I', '-c', '''
from importlib import metadata
import json
names=('hypnosis','carets','expose-interface','hidden-moves','hidden-moves-workspace','parse-md','backpack-store','func-seq','headless-spreadsheets','thoughtform','thoughtformula')
result={}
for name in names:
    try: d=metadata.distribution(name)
    except metadata.PackageNotFoundError: continue
    direct=json.loads(d.read_text('direct_url.json') or '{}')
    result[name]={'version':d.version,'commit':direct.get('vcs_info',{}).get('commit_id')}
print(json.dumps(result,sort_keys=True))
'''],check=True,capture_output=True,text=True,cwd=outside)
            receipt={'artifact': artifact.name, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                     'profile': profile or 'base', 'python': sys.version.split()[0], 'platform': sys.platform,
                     'installed':json.loads(probe.stdout),
                     'native_terminal':'POSIX pseudo-terminal' if profile=='application' and sys.platform!='win32' else 'not claimed in this profile'}
            receipts.append(receipt)
            print(json.dumps(receipt,sort_keys=True),flush=True)
    Path('qualification-'+(profile or 'base')+'.json').write_text(json.dumps({'schema':1,'artifacts':receipts},indent=2)+'\n')

if __name__ == '__main__':
    main()
