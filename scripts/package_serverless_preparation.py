"""Package only committed operator-function inputs, with a content-bound manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def package(output,commit='HEAD'):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new package directory')
    revision=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',commit+'^{commit}'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-rz',revision,'--','src','config','api','public','vercel.json','pyproject.toml'],cwd=ROOT)
    payload={}
    for entry in filter(None,tree.split(b'\0')):
        metadata,raw_path=entry.split(b'\t',1);mode,kind,blob=metadata.decode().split();name=raw_path.decode()
        if mode not in {'100644','100755'} or kind!='blob' or any(p.startswith('.') for p in Path(name).parts):
            raise ValueError('Only regular reviewed files may enter the operator package')
        if (name.startswith('api/') and name!='api/preparation.py' or
                name.startswith('public/') and name!='public/index.txt'):
            raise ValueError('Unexpected function or static asset in operator package')
        payload[name]=subprocess.check_output(['git','cat-file','blob',blob],cwd=ROOT)
    required={'api/preparation.py','src/acquisition/entrypoints/serverless_preparation.py',
              'vercel.json','pyproject.toml','public/index.txt'}
    if not required<=payload.keys():raise ValueError('Commit the complete reviewed operator entry point before packaging')
    config=json.loads(payload['vercel.json'])
    if config.get('outputDirectory')!='public' or config.get('functions',{}).get('api/preparation.py',{}).get('maxDuration')!=180:
        raise ValueError('The package needs an explicit public directory and bounded function configuration')
    manifest={'schema':'serverless-preparation-package/v1','source_commit':revision,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(payload.items())}}
    output.mkdir(parents=True)
    for name,raw in payload.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (output/'serverless-preparation-source.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--commit',default='HEAD');args=parser.parse_args()
    manifest=package(args.output,args.commit)
    print(json.dumps({'source_commit':manifest['source_commit'],'files':len(manifest['files'])}))
