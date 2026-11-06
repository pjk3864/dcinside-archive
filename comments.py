"""Read the public comment endpoint used by DC's own comment.js.

No login cookies, author IDs, IP addresses, or source-page nonces are stored.
"""
import html
import re
import time
from urllib.parse import urljoin

import bleach
from bs4 import BeautifulSoup
import requests

ENDPOINT = 'https://gall.dcinside.com/board/comment/'
COMMENT_VERSION = 1
SAFE_TAGS = {'p','div','span','br','b','strong','i','em','u','s','a','img',
             'video','source','audio','blockquote'}
SAFE_ATTRS = {'*':['class','title'],'a':['href','rel'],
              'img':['src','alt','loading'],
              'video':['src','poster','controls','muted','autoplay','loop','playsinline'],
              'audio':['src','controls'],'source':['src','type']}


class CommentFetchError(RuntimeError):
    pass


def source_mapping(doc, field, fallback):
    text = str(doc)
    patterns = [rf'''\.data\(\s*['"]{field}['"]\s*,\s*['"]([^'"]+)['"]''',
                rf'''\b{field}\s*:\s*['"]([^'"]+)['"]''']
    for pattern in patterns:
        match = re.search(pattern,text)
        if match:
            return match.group(1)
    return fallback


def fetch_comment_pages(s, post, doc, max_pages=300):
    token = doc.select_one('#e_s_n_o')
    if token is None or not token.get('value'):
        raise CommentFetchError('Comment source-page token is missing')
    records, seen, reported = [], set(), 0
    for page in range(1,max_pages+1):
        data = {'id':'dcbest','no':post['id'],
                'cmt_id':source_mapping(doc,'comment_id','dcbest'),
                'cmt_no':source_mapping(doc,'comment_no',post['id']),
                'e_s_n_o':token['value'],'comment_page':str(page),'sort':'D',
                'prevCnt':'','_GALLTYPE_':'G','focus_cno':'','focus_pno':'',
                'secret_article_key':'','clean':'','nptest':''}
        payload = None
        # This POST only reads comments, so retrying it cannot post a comment.
        for attempt in range(4):
            try:
                r = s.post(ENDPOINT,data=data,
                           headers={'Referer':post['source_url'],
                                    'X-Requested-With':'XMLHttpRequest'},timeout=(15,45))
                if r.status_code in (429,500,502,503,504) and attempt < 3:
                    time.sleep(min(30,2 ** (attempt+1)))
                    continue
                r.raise_for_status()
                payload = r.json()
                break
            except (requests.Timeout,requests.ConnectionError,ValueError):
                if attempt == 3:
                    raise CommentFetchError('Comment response unavailable or not JSON')
                time.sleep(2 ** (attempt+1))
        if not isinstance(payload,dict) or 'total_cnt' not in payload or 'comments' not in payload:
            raise CommentFetchError('Unexpected comment response schema')
        try:
            reported = int(str(payload['total_cnt']).replace(',',''))
        except (ValueError,TypeError) as error:
            raise CommentFetchError('Invalid comment count') from error
        rows = payload['comments'] or []
        if not isinstance(rows,list):
            raise CommentFetchError('Invalid comment rows')
        if not rows:
            if reported > len(seen):
                raise CommentFetchError(f'Incomplete comments: {len(seen)}/{reported}')
            return records,reported
        added = 0
        for row in rows:
            if not isinstance(row,dict) or 'no' not in row:
                raise CommentFetchError('Invalid comment row')
            key = str(row['no'])
            if key in seen:
                continue
            seen.add(key)
            records.append(row)
            added += 1
        if len(seen) >= reported:
            return records,reported
        if not added:
            raise CommentFetchError(f'Comment pagination repeated: {len(seen)}/{reported}')
        time.sleep(0.5)
    raise CommentFetchError('Comment pagination safety limit reached')


def normalize_comments(rows, post, download):
    """Preserve text, media and parent IDs; discard source controls and identities."""
    comments, warnings = [], []
    for row in rows:
        if row.get('nicktype') == 'COMMENT_BOY':
            continue  # Site-inserted promotional bot, not an archived reader.
        deleted = row.get('del_yn') == 'Y'
        memo = '삭제된 댓글입니다.' if deleted else str(row.get('memo') or '')
        fragment = BeautifulSoup(memo,'html.parser')
        for tag in fragment.select('script,style,iframe,object,embed,form,button,input'):
            tag.decompose()
        for tag in fragment.find_all(True):
            if tag.name == 'img':
                tag['src'] = tag.get('data-original') or tag.get('data-src') or tag.get('src','')
                tag['loading'] = 'lazy'
            for attr in ('src','poster'):
                if tag.get(attr):
                    tag[attr] = download(urljoin(post['source_url'],tag[attr]),warnings)
            if tag.name == 'a' and tag.get('href'):
                tag['href'] = urljoin(post['source_url'],tag['href'])
                tag['rel'] = 'noopener noreferrer'
            if tag.name in ('video','audio'):
                tag['controls'] = 'controls'
            if tag.name == 'video' and 'written_dccon' in tag.get('class',[]):
                for attr in ('muted','autoplay','loop','playsinline'):
                    tag[attr] = attr
        body_html = bleach.clean(str(fragment),tags=SAFE_TAGS,attributes=SAFE_ATTRS,
                                 protocols=['http','https'],strip=True)
        author = BeautifulSoup(html.unescape(str(row.get('name') or '익명')),'html.parser').get_text(' ',strip=True)
        parent = str(row.get('c_no') or '')
        comments.append({'id':str(row['no']),'parent_id':parent if parent != '0' else '',
                         'author':'삭제됨' if deleted else author,
                         'published':str(row.get('reg_date') or ''),
                         'depth':1 if str(row.get('depth') or '0') != '0' else 0,
                         'body':fragment.get_text('\n',strip=True),'body_html':body_html,
                         'deleted':deleted})
    return comments,warnings
