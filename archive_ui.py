"""Rendering-only template copied from the owner's current Dogdrip archive.

Keep structure, spacing, colors, pagination and comment layout shared. Only site
labels, local read-state keys and DC-specific media enhancements differ.
"""
import html
from datetime import datetime

POSTS_PER_LIST_PAGE = 20
PAGER_WINDOW_SIZE = 10
SEARCH_LIST_SCRIPT = '<script id="archive-search">\n(() => {\n  const form = document.querySelector("#archive-search");\n  const input = document.querySelector("#archive-search-input");\n  const status = document.querySelector("#archive-search-status");\n  const results = document.querySelector("#archive-search-results");\n  const list = document.querySelector("#archive-post-list");\n  const pager = document.querySelector(".pager");\n  let entries;\n\n  const reset = () => {\n    results.hidden = true;\n    results.replaceChildren();\n    list.hidden = false;\n    pager.hidden = false;\n    status.textContent = "";\n  };\n  const showResult = (entry) => {\n    const link = document.createElement("a");\n    link.className = "post-row";\n    link.href = `posts/${entry.id}.html`;\n    link.dataset.postId = entry.id;\n    const title = document.createElement("span");\n    title.className = "row-title";\n    title.textContent = entry.title;\n    link.append(title);\n    return link;\n  };\n  form.addEventListener("submit", async (event) => {\n    event.preventDefault();\n    const query = input.value.trim().toLocaleLowerCase("ko-KR");\n    if (!query) return reset();\n    status.textContent = "검색 중…";\n    try {\n      entries ||= await fetch("archive.json", { cache: "force-cache" }).then((response) => {\n        if (!response.ok) throw new Error("archive index unavailable");\n        return response.json();\n      });\n      const matches = entries.filter((entry) => entry.title.toLocaleLowerCase("ko-KR").includes(query));\n      results.replaceChildren(...matches.map(showResult));\n      results.hidden = false;\n      list.hidden = true;\n      pager.hidden = true;\n      status.textContent = `“${input.value.trim()}” 검색 결과 ${matches.length}개`;\n    } catch (_) {\n      status.textContent = "검색 결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";\n    }\n  });\n  form.addEventListener("reset", () => setTimeout(reset, 0));\n})();\n</script>'
READ_LIST_SCRIPT = '<script id="archive-read-list">\n(() => {\n  const key = "dcinside-archive-read-posts";\n  try {\n    const read = new Set(JSON.parse(localStorage.getItem(key) || "[]"));\n    document.querySelectorAll(".post-row[data-post-id]").forEach((row) => {\n      if (read.has(row.dataset.postId)) row.classList.add("is-read");\n      row.addEventListener("click", () => {\n        read.add(row.dataset.postId);\n        localStorage.setItem(key, JSON.stringify([...read]));\n      });\n    });\n  } catch (_) {}\n})();\n</script>'
READ_POST_SCRIPT = '<script id="archive-read-post">\n(() => {\n  const key = "dcinside-archive-read-posts";\n  try {\n    const read = new Set(JSON.parse(localStorage.getItem(key) || "[]"));\n    read.add(document.body.dataset.postId);\n    localStorage.setItem(key, JSON.stringify([...read]));\n  } catch (_) {}\n})();\n</script>'

# Keep read tracking working for dynamically generated global-search results too.
SEARCH_LIST_SCRIPT = SEARCH_LIST_SCRIPT.replace(
    'link.dataset.postId = entry.id;',
    '''link.dataset.postId = entry.id;
    try {
      const key = "dcinside-archive-read-posts";
      const read = new Set([...JSON.parse(localStorage.getItem(key) || "[]"), ...JSON.parse(localStorage.getItem("dc-read") || "[]")]);
      if (read.has(entry.id)) link.classList.add("is-read");
      link.addEventListener("click", () => {
        read.add(entry.id);
        localStorage.setItem(key, JSON.stringify([...read]));
      });
    } catch (_) {}''')
for _name in ('READ_LIST_SCRIPT','READ_POST_SCRIPT'):
    globals()[_name] = globals()[_name].replace(
        'const read = new Set(JSON.parse(localStorage.getItem(key) || "[]"));',
        'const read = new Set([...JSON.parse(localStorage.getItem(key) || "[]"), ...JSON.parse(localStorage.getItem("dc-read") || "[]")]);')


def list_page_path(page_number):
    return 'index.html' if page_number == 1 else f'page-{page_number}.html'

def generate_index_html(entries, page_number=1):
    """Generate one 20-item archive list page with simple page navigation."""
    total_pages = max(1, (len(entries) + POSTS_PER_LIST_PAGE - 1) // POSTS_PER_LIST_PAGE)
    start = (page_number - 1) * POSTS_PER_LIST_PAGE
    page_entries = entries[start:start + POSTS_PER_LIST_PAGE]
    rows = []
    for entry in page_entries:
        rows.append(f'''<a class="post-row" data-post-id="{html.escape(entry['id'], quote=True)}" href="posts/{entry['id']}.html">\n  <span class="row-title">{html.escape(entry['title'])}</span>\n</a>''')
    pager_group_start = (page_number - 1) // PAGER_WINDOW_SIZE * PAGER_WINDOW_SIZE + 1
    pager_group_end = min(pager_group_start + PAGER_WINDOW_SIZE - 1, total_pages)
    pager_parts = []
    if pager_group_start > 1:
        pager_parts.append(f'<a class="page-link page-shift" href="{list_page_path(pager_group_start - 1)}" aria-label="이전 페이지 묶음">이전</a>')
    pager_parts.extend((f'''<a class="page-link{(' current' if number == page_number else '')}" href="{list_page_path(number)}"{(' aria-current="page"' if number == page_number else '')}>{number}</a>''' for number in range(pager_group_start, pager_group_end + 1)))
    if pager_group_end < total_pages:
        pager_parts.append(f'<a class="page-link page-shift" href="{list_page_path(pager_group_end + 1)}" aria-label="다음 페이지 묶음">다음</a>')
    pager = ''.join(pager_parts)
    updated_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""<!doctype html>\n<html lang="ko">\n<head>\n  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css" referrerpolicy="no-referrer">\n  <title>디시 아카이브</title>\n  <style>\n    :root {{ --blue:#4ba3ff; --ink:#e9edf2; --muted:#9aa3ae; --line:#363b43; --panel:#202329; --panel-deep:#17191d; }}\n    * {{ box-sizing:border-box; }} body {{ margin:0; background:#111317; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif; }} .sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}\n    .site {{ max-width:960px; min-height:100vh; margin:auto; background:var(--panel); }}\n    header {{ display:flex; align-items:center; gap:12px; height:54px; padding:0 20px; background:var(--panel-deep); border-bottom:1px solid var(--line); }}\n    h1 {{ margin:0; font-size:17px; }} .updated {{ margin:0; padding:13px 20px; color:var(--muted); border-bottom:1px solid var(--line); font-size:12px; }}\n    .search {{ display:flex; gap:8px; padding:12px 20px; border-bottom:1px solid var(--line); }} .search input {{ flex:1; min-width:0; border:1px solid var(--line); border-radius:5px; background:#111317; color:var(--ink); padding:9px 10px; font:inherit; }} .search input:focus {{ border-color:var(--blue); outline:2px solid color-mix(in srgb, var(--blue) 35%, transparent); }} .search button {{ border:1px solid var(--blue); border-radius:5px; background:var(--blue); color:#fff; cursor:pointer; padding:9px 12px; font:inherit; }} .search button[type="reset"] {{ background:transparent; border-color:var(--line); color:var(--ink); }} .search-status {{ min-height:20px; margin:0; padding:0 20px 10px; color:var(--muted); font-size:13px; }}\n    .post-row {{ display:block; min-height:62px; padding:19px 20px; color:inherit; text-decoration:none; border-bottom:1px solid var(--line); transition:background .15s; }}\n    .post-row:hover, .post-row:focus-visible {{ background:#292e36; outline:none; }} .post-row.is-read .row-title {{ color:#777f8a; }} .row-title {{ display:block; overflow:hidden; font-size:18px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }}\n    .pager {{ display:flex; flex-wrap:wrap; justify-content:center; gap:6px; padding:24px 16px; }} .page-link {{ min-width:34px; padding:8px 10px; border:1px solid var(--line); border-radius:5px; color:var(--ink); text-align:center; text-decoration:none; font-size:14px; }} .page-link.page-shift {{ min-width:52px; }} .page-link:hover,.page-link:focus-visible {{ border-color:var(--blue); color:var(--blue); outline:none; }} .page-link.current {{ background:var(--blue); border-color:var(--blue); color:#fff; pointer-events:none; }}\n    @media(max-width:640px) {{ header {{ height:50px; padding:0 14px; }} .updated,.search {{ padding-left:14px; padding-right:14px; }} .search-status {{ padding-left:14px; padding-right:14px; }} .post-row {{ min-height:55px; padding:16px 14px; }} .row-title {{ font-size:16px; }} .pager {{ gap:5px; padding:20px 10px; }} .page-link {{ min-width:32px; padding:7px 8px; }} }}\n  </style>\n</head>\n<body><main class="site"><header><i class="fa-solid fa-list" aria-hidden="true"></i><h1>디시 아카이브</h1></header><p class="updated">보관된 글 {len(entries)}개 · {page_number}/{total_pages} 페이지 · 마지막 수집 {updated_at}</p><form class="search" id="archive-search" role="search"><label class="sr-only" for="archive-search-input">글 제목 검색</label><input id="archive-search-input" type="search" placeholder="글 제목으로 지난 글 찾기" autocomplete="off"><button type="submit">검색</button><button type="reset">초기화</button></form><p class="search-status" id="archive-search-status" aria-live="polite"></p><section id="archive-post-list">{''.join(rows)}</section><section id="archive-search-results" hidden aria-label="검색 결과"></section><nav class="pager" aria-label="목록 페이지">{pager}</nav></main>{READ_LIST_SCRIPT}{SEARCH_LIST_SCRIPT}</body>\n</html>"""

def generate_post_html(post):
    """Generate one self-contained archived article page."""
    comments_html = generate_comments_html(post.get('archived_comments', []))
    return f'''<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css" referrerpolicy="no-referrer"><title>{html.escape(post['title'])} · 디시 아카이브</title>\n<style>body{{margin:0;background:#111317;color:#e9edf2;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif}}main{{max-width:960px;min-height:100vh;margin:auto;padding:28px 24px 48px;background:#202329}}.back,.source{{color:#4ba3ff;text-decoration:none;font-size:14px}}h1{{margin:20px 0 0;color:#f6f8fa;font-size:25px;line-height:1.42}}.meta{{margin:10px 0 20px;color:#9aa3ae;border-bottom:1px solid #363b43;padding-bottom:18px;font-size:13px}}.article{{font-size:16px;line-height:1.72;overflow-wrap:anywhere}}.article img,.article video{{display:block;max-width:100%;height:auto;margin:10px auto}}.article a{{color:#4ba3ff}}.archived-comments{{margin-top:42px;border-top:1px solid #363b43;padding-top:22px}}.archived-comments h2{{margin:0 0 14px;font-size:18px}}.comment{{padding:14px 0;border-top:1px solid #30353c}}.comment:first-of-type{{border-top:0}}.comment.is-reply{{margin-left:34px;padding-left:16px;border-left:2px solid #4ba3ff;background:#1b1e23}}.comment-reply-label{{color:#4ba3ff;font-size:12px;font-weight:600}}.comment-meta{{margin:0 0 7px;color:#9aa3ae;font-size:13px}}.comment-author{{color:#e9edf2;font-weight:600}}.comment-body{{margin:0;white-space:pre-wrap;font-size:15px;line-height:1.6;overflow-wrap:anywhere}}.comment-body img,.comment-body video{{display:block;max-width:100%;height:auto;margin:8px 0}}.comment-body a{{color:#4ba3ff}}@media(max-width:640px){{main{{padding:22px 16px 40px}}h1{{font-size:22px}}.comment.is-reply{{margin-left:18px;padding-left:12px}}}}</style></head>\n<body data-post-id="{html.escape(post['id'], quote=True)}"><main><a class="back" href="../index.html"><i class="fa-solid fa-arrow-left" aria-hidden="true"></i> 목록으로</a><h1>{html.escape(post['title'])}</h1><p class="meta"><i class="fa-regular fa-thumbs-up" aria-hidden="true"></i> {html.escape(post['votes'])} · <i class="fa-regular fa-comment" aria-hidden="true"></i> {html.escape(post['comments'])} · {html.escape(post['published'])} · <a class="source" href="{html.escape(post['source_url'], quote=True)}" target="_blank" rel="noopener noreferrer">원문</a></p><article class="article">{post['content']}</article>{comments_html}</main>{READ_POST_SCRIPT}</body></html>'''

def generate_comments_html(comments):
    """Render copied text and DCInside emoticons without page controls or active scripts."""
    if comments:
        rows = ''.join((f'''<div class="comment{(' is-reply' if comment.get('depth', 0) else '')}" data-depth="{int(comment.get('depth', 0))}"><p class="comment-meta">{('<span class="comment-reply-label">↳ 답글</span> · ' if comment.get('depth', 0) else '')}<span class="comment-author">{html.escape(comment['author'])}</span>{(' · ' + html.escape(comment['published']) if comment['published'] else '')}</p><div class="comment-body">{comment.get('body_html') or html.escape(comment['body'])}</div></div>''' for comment in comments))
        description = f'수집 당시 댓글 {len(comments)}개'
    else:
        rows = '<p class="comment-body">수집할 댓글이 없습니다.</p>'
        description = '수집 당시 댓글 없음'
    return f'<!-- archived-comments:start --><section class="archived-comments"><h2><i class="fa-regular fa-comments" aria-hidden="true"></i> 댓글</h2><p class="comment-meta">{description}</p>{rows}</section><!-- archived-comments:end -->'
