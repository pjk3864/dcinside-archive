"""Dogdrip archive's exact shared layout, adapted to DCInside metadata."""
from datetime import datetime
import hashlib
import json
import re

from bs4 import BeautifulSoup
import archive_ui as ui

UI_VERSION = 2
EXTRA_CSS = '''<style id="dc-comment-media">.comment-body .written_dccon{display:inline-block;max-width:200px;max-height:200px;object-fit:contain;vertical-align:top}.comment-body .bigdccon{max-width:300px;max-height:300px}.comment-body .coment_dccon_txt{display:inline-flex;min-width:110px;min-height:110px;max-width:240px;align-items:center;justify-content:center;padding:12px;background:#fff;color:#111;font-size:22px;font-weight:700;white-space:normal}.archive-notice{color:#9aa3ae;font-size:13px}.article table{display:block;overflow:auto;max-width:100%}.comment-body audio{max-width:100%}</style>'''


def comment_pending_section():
    return '<!-- archived-comments:start --><section class="archived-comments"><h2>댓글</h2><p class="comment-meta">댓글 보관 대기 중입니다. 원문 응답 오류가 있으면 다음 실행에서 다시 수집합니다.</p></section><!-- archived-comments:end -->'


def article_page(entry,content,comments=None):
    post = dict(entry,content=content,archived_comments=comments or [],
                votes=str(entry.get('votes','—')),
                comments=str(len(comments)) if comments is not None else '수집 대기',
                published=str(entry.get('published','')))
    page = ui.generate_post_html(post)
    if comments is None:
        page = re.sub(r'<!-- archived-comments:start -->.*?<!-- archived-comments:end -->',
                      lambda _:comment_pending_section(),page,flags=re.S)
    if entry.get('media_warnings'):
        page = page.replace('<article class="article">','<p class="archive-notice">일부 외부·대용량·응답 실패 미디어는 원본 링크로 남아 있습니다.</p><article class="article">',1)
    if entry.get('comment_media_retry_needed'):
        page = page.replace('</main>','<p class="archive-notice">일부 댓글 미디어는 원본 링크로 남아 있으며 다시 확인할 예정입니다.</p></main>',1)
    return page.replace('</head>',EXTRA_CSS+'</head>',1)


def list_page(entries,number):
    page = ui.generate_index_html(entries,number)
    collected = max((e.get('archived_at','') for e in entries),default='')
    if collected:
        stamp = datetime.fromisoformat(collected).strftime('%Y-%m-%d %H:%M')
        page = re.sub(r'마지막 수집 \d{4}-\d{2}-\d{2} \d{2}:\d{2}',
                      '마지막 수집 '+stamp+' (방콕)',page)
    digest = hashlib.sha256(json.dumps(entries,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    page = page.replace('fetch("archive.json",',f'fetch("archive.json?v={digest}",')
    return page


def saved_article(page):
    doc = BeautifulSoup(page,'html.parser')
    article = doc.select_one('article')
    if article is None:
        raise ValueError('Saved article body missing')
    return ''.join(str(child) for child in article.contents)
