"""Archive publicly accessible DCInside real-time best posts, with checkpoints."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import bleach
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
BASE = 'https://gall.dcinside.com'
LIST = BASE + '/board/lists/?id=dcbest&page={}'
MAX_MEDIA = 12 * 1024 * 1024
MEDIA_ARCHIVE_VERSION = 2
TAGS = frozenset({'p','div','span','br','b','strong','i','em','u','s','blockquote',
                  'ul','ol','li','a','img','video','audio','source','h1','h2','h3',
                  'table','tbody','tr','th','td','hr','pre','code','figure','figcaption'})
CSS = '''body{margin:0;background:#11151d;color:#e5eaf2;font:16px/1.75 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px}a{color:#9bc8ff;text-decoration:none}a:hover{text-decoration:underline}h1{font-size:27px;line-height:1.4}header,footer{color:#a9b5c9;margin:20px 0}article{overflow-wrap:anywhere}article img,article video{max-width:100%;height:auto}article table{max-width:100%;overflow:auto;display:block}li.post{padding:14px 0;border-bottom:1px solid #2b3342;list-style:none}.meta{font-size:13px;color:#9ba9bd}ul{padding-left:20px}ul.posts{padding:0}nav{display:flex;gap:16px;flex-wrap:wrap;padding:20px 0}input{width:min(90%,500px);padding:12px;background:#1b2432;color:white;border:1px solid #43516a;border-radius:6px}.notice{padding:12px;background:#202b3b;border-radius:6px}a.read{color:#778399}'''


def now():
    return datetime.now(ZoneInfo('Asia/Bangkok')).isoformat(timespec='seconds')


def load(name, default):
    path = ROOT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def session():
    s = requests.Session()
    s.headers.update({'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Referer':BASE + '/'})
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429,500,502,503,504],
                  allowed_methods=['GET'], respect_retry_after_header=True)
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s


def document(s, url):
    for attempt in range(3):
        r = s.get(url, timeout=(15,60))
        r.raise_for_status()
        if r.content:
            return BeautifulSoup(r.content, 'html.parser')
        time.sleep(2 ** attempt)
    raise RuntimeError('Empty response: ' + url)


def parse_list(doc):
    result = []
    for row in doc.select('tr.ub-content'):
        # Notices/advertisements must not be treated as new archive posts.
        number = row.select_one('.gall_num')
        if not number or not number.get_text(strip=True).isdigit():
            continue
        ident = row.get('data-no', '')
        link = row.select_one('td.gall_tit a[href*="/view/"]')
        if not re.fullmatch(r'\d+', ident) or not link:
            continue
        copy = BeautifulSoup(str(link), 'html.parser')
        for tag in copy.select('.thumimg, .icon_img'):
            tag.decompose()
        result.append({'id':ident, 'title':copy.get_text(' ',strip=True),
                       'source_url':BASE + '/board/view/?id=dcbest&no=' + ident})
    if not result:
        raise RuntimeError('No normal posts found; source may be blocked or changed')
    return result


def media(s, url, ident, referer, warnings, attempt=0):
    parsed = urlparse(url)
    if parsed.scheme not in ('http','https'):
        return ''
    host = (parsed.hostname or '').lower()
    # Download DC's own public media only; do not follow arbitrary article URLs.
    if not any(host == h or host.endswith('.' + h) for h in ('dcinside.com','dcinside.co.kr')):
        warnings.append('외부 미디어 원본 유지: ' + url)
        return url
    try:
        with s.get(url, headers={'Referer':referer}, stream=True, timeout=(15,60)) as r:
            r.raise_for_status()
            kind = r.headers.get('Content-Type','').split(';')[0].lower()
            extensions = {'image/jpeg':'.jpg','image/png':'.png','image/gif':'.gif',
                          'image/webp':'.webp','image/avif':'.avif','video/mp4':'.mp4',
                          'video/webm':'.webm','audio/mpeg':'.mp3'}
            if int(r.headers.get('Content-Length',0)) > MAX_MEDIA:
                raise ValueError('Media exceeds 12 MiB')
            chunks, size = [], 0
            for chunk in r.iter_content(65536):
                size += len(chunk)
                if size > MAX_MEDIA:
                    raise ValueError('Media exceeds 12 MiB')
                chunks.append(chunk)
            content = b''.join(chunks)
            if not content:
                raise ValueError('Empty media')
            if kind not in extensions:
                # DC sometimes serves valid images as application/octet-stream.
                if content.startswith(b'\xff\xd8\xff'):
                    kind = 'image/jpeg'
                elif content.startswith(b'\x89PNG\r\n\x1a\n'):
                    kind = 'image/png'
                elif content.startswith((b'GIF87a',b'GIF89a')):
                    kind = 'image/gif'
                elif content[:4] == b'RIFF' and content[8:12] == b'WEBP':
                    kind = 'image/webp'
                elif content[4:8] == b'ftyp' and content[8:12] in (b'avif',b'avis'):
                    kind = 'image/avif'
                elif content[4:8] == b'ftyp':
                    kind = 'video/mp4'
                else:
                    raise ValueError('Unsupported media type: ' + kind)
            digest = hashlib.sha256(content).hexdigest()[:24]
            path = Path('assets') / ident / (digest + extensions[kind])
            (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / path).write_bytes(content)
            return '../' + path.as_posix()
    except (requests.RequestException, ValueError) as error:
        if isinstance(error,ValueError) and str(error) == 'Empty media' and attempt < 2:
            time.sleep(2 ** (attempt + 1))
            return media(s,url,ident,referer,warnings,attempt + 1)
        warnings.append('미디어 원본 유지 (' + str(error) + '): ' + url)
        return url


def archive_post(s, post):
    doc = document(s, post['source_url'])
    body = doc.select_one('.write_div')
    title = doc.select_one('.title_subject')
    if body is None or title is None:
        raise RuntimeError('Post body missing: ' + post['source_url'])
    warnings = []
    for tag in body.select('iframe,embed'):
        source = tag.get('src','')
        if source.startswith(('https://','http://','//')):
            link = doc.new_tag('a',href=urljoin(post['source_url'],source))
            link.string = '[외부 동영상 원본 열기]'
            tag.replace_with(link)
        else:
            tag.decompose()
    for tag in body.select('script,style,object,form,input,button'):
        tag.decompose()
    for tag in body.find_all(True):
        if tag.name == 'img':
            # Lazy-loaded DC images put the real URL in data-original, not src.
            tag['src'] = tag.get('data-original') or tag.get('data-src') or tag.get('src','')
        for attr in ('src','poster'):
            value = tag.get(attr)
            if not value:
                continue
            absolute = urljoin(post['source_url'], value)
            tag[attr] = media(s, absolute, post['id'], post['source_url'], warnings)
        if tag.name == 'a' and tag.get('href'):
            tag['href'] = urljoin(post['source_url'],tag['href'])
            tag['rel'] = 'noopener noreferrer'
        if tag.name in ('video','audio'):
            tag['controls'] = 'controls'
        if tag.name == 'img':
            tag['loading'] = 'lazy'
    content = bleach.clean(str(body), tags=TAGS,
                           attributes={'*':['title'], 'a':['href','rel'],
                                       'img':['src','alt','loading'],
                                       'video':['src','poster','controls'],
                                       'audio':['src','controls'],
                                       'source':['src','type'], 'td':['colspan','rowspan']},
                           protocols=['http','https'], strip=True)
    entry = dict(post, title=title.get_text(' ',strip=True), archived_at=now(),
                 media_warnings=warnings, media_archive_version=MEDIA_ARCHIVE_VERSION)
    entry['media_retry_needed'] = any(
        w.startswith('미디어 원본 유지') and 'Media exceeds' not in w and 'Unsupported media type' not in w
        for w in warnings
    )
    date = doc.select_one('.gall_date')
    entry['published'] = date.get('title',date.get_text(strip=True)) if date else ''
    notice = '<p class="notice">일부 미디어는 원본 링크로 남아 있습니다.</p>' if warnings else ''
    page = shell(entry['title'], '<header><a href="../index.html">← 디시 아카이브</a></header>'
                 + '<h1>' + html.escape(entry['title']) + '</h1><p class="meta">원문 작성(KST): '
                 + html.escape(entry['published']) + ' · 보관(Bangkok): ' + entry['archived_at']
                 + ' · <a rel="noreferrer" href="' + html.escape(post['source_url'],quote=True)
                 + '">원문 보기</a></p>' + notice + '<article>' + content + '</article>'
                 + '<footer>공개 본문과 지원 미디어를 보관합니다. 댓글은 보관하지 않습니다.</footer>')
    path = ROOT / 'posts' / (post['id'] + '.html')
    path.parent.mkdir(exist_ok=True)
    path.write_text(page,encoding='utf-8')
    return entry


def shell(title, content):
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>' + html.escape(title) + '</title><style>' + CSS + '</style></head><body><main>' + content + '</main></body></html>'


def render(entries):
    entries = sorted(entries,key=lambda e:int(e['id']),reverse=True)
    count = max(1,(len(entries)+49)//50)
    def link(n):
        return 'index.html' if n == 1 else f'page-{n}.html'
    for number in range(1,count+1):
        nav = '<nav>' + ' '.join(f'<a href="{link(n)}">{n}</a>' for n in range(max(1,number-4),min(count,number+4)+1)) + '</nav>'
        rows = ''.join('<li class="post"><a data-post="' + e['id'] + '" href="posts/' + e['id'] + '.html">' + html.escape(e['title']) + '</a><div class="meta">' + html.escape(e.get('published','')) + '</div></li>' for e in entries[(number-1)*50:number*50])
        content = '<h1>디시 아카이브</h1><header>실시간 베스트 · 총 ' + str(len(entries)) + '개 · 매일 방콕 오전 10시 예약<br>개인 열람용 비공식 보관소 · <a href="https://gall.dcinside.com/board/lists/?id=dcbest">원본 실베</a></header><input id="search" type="search" placeholder="이 페이지 제목 검색" aria-label="제목 검색">' + nav + '<ul class="posts">' + rows + '</ul>' + nav
        content += '''<script>const seen=JSON.parse(localStorage.getItem('dc-read')||'[]');document.querySelectorAll('[data-post]').forEach(a=>{if(seen.includes(a.dataset.post))a.classList.add('read');a.onclick=()=>{if(!seen.includes(a.dataset.post))seen.push(a.dataset.post);localStorage.setItem('dc-read',JSON.stringify(seen));};});document.getElementById('search').oninput=e=>document.querySelectorAll('li.post').forEach(li=>li.hidden=!li.textContent.toLowerCase().includes(e.target.value.toLowerCase()));</script>'''
        (ROOT/link(number)).write_text(shell('디시 아카이브',content),encoding='utf-8')
    (ROOT/'.nojekyll').touch()


def publish():
    subprocess.run(['git','add','archive.json','pending.json','state.json','index.html','posts','assets','.nojekyll'],cwd=ROOT,check=True)
    for page in ROOT.glob('page-*.html'):
        subprocess.run(['git','add',page.name],cwd=ROOT,check=True)
    changed = subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode
    if changed:
        subprocess.run(['git','commit','--quiet','-m','Update real-time best archive'],cwd=ROOT,check=True)
    for attempt in range(5):
        result = subprocess.run(['git','push','origin','HEAD:main'],cwd=ROOT)
        if result.returncode == 0:
            return
        time.sleep(min(60,2 ** (attempt+1)))
    raise RuntimeError('Git push failed; local checkpoint is preserved')


def collect(pages=10, do_publish=False, workers=1, retry_media=False):
    s = session()
    entries = load('archive.json',[])
    state = load('state.json',{})
    pending = {p['id']:p for p in load('pending.json',[])}
    for entry in entries:
        media_failed = entry.get('media_retry_needed') or any(
            w.startswith('미디어 원본 유지') and 'Media exceeds' not in w and 'Unsupported media type' not in w
            for w in entry.get('media_warnings',[])
        )
        if media_failed or (retry_media and entry.get('media_warnings')) or entry.get('media_archive_version',0) < MEDIA_ARCHIVE_VERSION:
            pending[entry['id']] = {k:entry[k] for k in ('id','title','source_url')}
    known = {p['id'] for p in entries if p['id'] not in pending}
    highwater = int(state.get('last_seen_id',0))
    discovered = []
    # Bootstrap exactly ten source list pages. Daily runs scan through the last
    # completed discovery boundary, rather than silently skipping older failures.
    limit = pages if not state.get('initialized') else 200
    boundary_found = not state.get('initialized')
    for number in range(1,limit+1):
        rows = parse_list(document(s,LIST.format(number)))
        print(f'List {number}: {len(rows)} posts',flush=True)
        discovered.extend(p for p in rows if int(p['id']) > highwater and p['id'] not in known)
        if highwater and min(int(p['id']) for p in rows) <= highwater:
            boundary_found = True
            break
        time.sleep(0.7)
    if not boundary_found:
        raise RuntimeError('Discovery safety limit reached; refusing to skip unseen posts')
    pending.update({p['id']:p for p in discovered})
    pending = {i:p for i,p in pending.items() if i not in known}
    if discovered:
        state['last_seen_id'] = max(highwater,max(int(p['id']) for p in discovered))
    state.update(initialized=True,bootstrap_pages=pages,last_discovery_at=now())
    save('state.json',state)
    save('pending.json',list(pending.values()))
    save('archive.json',entries)
    (ROOT/'posts').mkdir(exist_ok=True)
    (ROOT/'assets').mkdir(exist_ok=True)
    render(entries)
    if do_publish:
        publish()
    failures = []
    def process(post):
        try:
            entry = archive_post(s if workers == 1 else session(),post)
            return post,entry,None
        except (requests.RequestException,RuntimeError,ValueError) as error:
            return post,None,error
        finally:
            time.sleep(0.5)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(process,list(pending.values())) if workers > 1 else map(process,list(pending.values()))
        for index,(post,entry,error) in enumerate(results,1):
            print(f'Archive {index}/{len(pending)}: {post["id"]} {post["title"]}',flush=True)
            if error is None:
                entries = [e for e in entries if e['id'] != post['id']] + [entry]
                known.add(post['id'])
                save('archive.json',entries)
                save('pending.json',[p for i,p in pending.items() if i not in known])
            else:
                print(f'FAILED {post["id"]}: {error}',flush=True)
                failures.append(post['id'])
            if index % 20 == 0:
                render(entries)
                if do_publish:
                    publish()
    render(entries)
    state['last_run_at'] = now()
    state['last_run_failed_ids'] = failures
    save('state.json',state)
    if do_publish:
        publish()
    print(f'Finished: {len(entries)} archived; {len(failures)} pending failures',flush=True)
    if failures:
        raise RuntimeError('Some posts failed; published successes and retained retry queue')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pages',type=int,default=10)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=1)
    parser.add_argument('--retry-media',action='store_true')
    args = parser.parse_args()
    if args.render:
        render(load('archive.json',[]))
    else:
        collect(args.pages,args.publish,args.workers,args.retry_media)
