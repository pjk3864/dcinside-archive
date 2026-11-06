"""Build HTML-only Pages artifact; preserved media is served from this commit."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent


def build():
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}',sha):
        raise ValueError('Invalid commit SHA')
    base = f'https://raw.githubusercontent.com/pjk3864/dcinside-archive/{sha}/assets/'
    out = ROOT / '_site'
    (out/'posts').mkdir(parents=True,exist_ok=True)
    entries = json.loads((ROOT/'archive.json').read_text(encoding='utf-8'))
    paths = list(ROOT.glob('*.html')) + [ROOT/'posts'/(e['id']+'.html') for e in entries]
    for path in paths:
        text = path.read_text(encoding='utf-8')
        for match in re.finditer(r'(?:src|poster)="\.\./(assets/[^"<>]+)"',text):
            if not (ROOT/match.group(1)).is_file():
                raise ValueError('Missing archived asset: ' + match.group(1))
        text = text.replace('="../assets/','="' + base)
        target = out/path.relative_to(ROOT)
        target.write_text(text,encoding='utf-8')
    (out/'.nojekyll').touch()
    (out/'deployment.json').write_text(json.dumps({'commit':sha,'post_count':len(entries)},indent=2),encoding='utf-8')
    print(f'Built {len(entries)} posts for {sha}')


if __name__ == '__main__':
    build()
