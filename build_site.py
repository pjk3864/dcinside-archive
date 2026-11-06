"""Build HTML-only Pages artifact; preserved media is served from this commit."""
import json
from pathlib import Path
import re
import subprocess
from storage import sealed_media_url

ROOT = Path(__file__).resolve().parent


def build():
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}',sha):
        raise ValueError('Invalid commit SHA')
    base = f'https://raw.githubusercontent.com/pjk3864/dcinside-archive/{sha}/assets/'
    out = ROOT / '_site'
    (out/'posts').mkdir(parents=True,exist_ok=True)
    entries = json.loads((ROOT/'archive.json').read_text(encoding='utf-8'))
    locations_path=ROOT/'media-locations.json'
    locations=json.loads(locations_path.read_text(encoding='utf-8')) if locations_path.exists() else {}
    # Like Dogdrip: deploy only HTML, and validate media against the Git tree.
    # This also supports sparse checkout without downloading gigabytes for Pages.
    tracked=set(subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD','assets'],cwd=ROOT,text=True).splitlines())
    def media_url(match):
        path=match.group(1)
        if path in locations:
            return '="'+sealed_media_url(locations[path])+'"'
        if path not in tracked:
            raise ValueError('Missing archived asset: '+path)
        return '="'+base+path[len('assets/'):]+'"'
    paths = list(ROOT.glob('*.html')) + [ROOT/'posts'/(e['id']+'.html') for e in entries]
    for path in paths:
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'="\.\./(assets/[^"<>]+)"',media_url,text)
        target = out/path.relative_to(ROOT)
        target.write_text(text,encoding='utf-8')
    (out/'.nojekyll').touch()
    (out/'archive.json').write_text(json.dumps(entries,ensure_ascii=False),encoding='utf-8')
    (out/'deployment.json').write_text(json.dumps({'commit':sha,'post_count':len(entries)},indent=2),encoding='utf-8')
    size=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    if size >= 900_000_000:
        raise ValueError('Pages artifact is approaching its size limit; split storage before deploying')
    print(f'Built {len(entries)} posts for {sha}; HTML artifact {size:,} bytes')


if __name__ == '__main__':
    build()
