import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
from bs4 import BeautifulSoup

from comments import fetch_comment_pages, normalize_comments, CommentFetchError
from presentation import article_page,list_page
from storage import sealed_media_url


POST={'id':'10','title':'제목','source_url':'https://gall.dcinside.com/board/view/?id=dcbest&no=10','published':''}


class CommentTests(unittest.TestCase):
    def test_failed_refresh_preserves_saved_comments(self):
        import archiver as a
        saved=[{'id':'1','author':'기존 닉네임','published':'오늘','depth':0,'body':'기존 댓글','body_html':'기존 댓글'}]
        doc=BeautifulSoup('<span class="title_subject">제목</span><div class="write_div">본문</div>','html.parser')
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)),patch.object(a,'document',return_value=doc):
            a.save('comments/10.json',saved)
            a.save('archive.json',[dict(POST,comment_archive_version=1)])
            result=a.archive_post(None,POST)
            self.assertEqual(result['comment_status'],'pending_refresh')
            self.assertIn('기존 댓글',(Path(tmp)/'posts/10.html').read_text(encoding='utf-8'))
            self.assertEqual(a.load('comments/10.json',[]),saved)

    def test_all_pages_and_duplicate_rows(self):
        s=MagicMock()
        values=[{'total_cnt':'3','comments':[{'no':'1'},{'no':'2'}]},
                {'total_cnt':'3','comments':[{'no':'2'},{'no':'3'}]}]
        s.post.side_effect=[MagicMock(status_code=200,json=MagicMock(return_value=value)) for value in values]
        doc=BeautifulSoup('<input id="e_s_n_o" value="fixture-nonce">','html.parser')
        with patch('comments.time.sleep'):
            rows,total=fetch_comment_pages(s,POST,doc)
        self.assertEqual([r['no'] for r in rows],['1','2','3'])
        self.assertEqual(total,3)
        self.assertEqual(s.post.call_args.kwargs['data']['comment_page'],'2')

    def test_empty_or_partial_response_is_not_no_comments(self):
        doc=BeautifulSoup('<input id="e_s_n_o" value="fixture-nonce">','html.parser')
        s=MagicMock()
        s.post.return_value.status_code=200
        s.post.return_value.json.return_value={'total_cnt':2,'comments':[]}
        with self.assertRaises(CommentFetchError):
            fetch_comment_pages(s,POST,doc)
        s.post.return_value.json.return_value={'error':'blocked'}
        with self.assertRaises(CommentFetchError):
            fetch_comment_pages(s,POST,doc)

    def test_replies_photos_and_emoticons_without_active_scripts(self):
        rows=[{'no':1,'depth':0,'name':'익명','memo':'텍스트<img class="written_dccon" src="//dcimg5.dcinside.com/con.gif" onerror="bad()"><script>bad()</script>','ip':'not-stored','user_id':'not-stored'},
              {'no':2,'c_no':1,'depth':1,'name':'답글','memo':'<video class="written_dccon" src="https://dcimg5.dcinside.com/con.mp4"></video>'}]
        download=MagicMock(side_effect=lambda url,warnings:'../assets/comment-media/'+('con.mp4' if '.mp4' in url else 'con.gif'))
        comments,warnings=normalize_comments(rows,POST,download)
        self.assertEqual(comments[1]['parent_id'],'1')
        self.assertEqual(comments[1]['depth'],1)
        self.assertIn('../assets/comment-media/con.gif',comments[0]['body_html'])
        self.assertIn('muted',comments[1]['body_html'])
        self.assertNotIn('onerror',comments[0]['body_html'])
        self.assertNotIn('bad()',comments[0]['body_html'])
        self.assertNotIn('ip',comments[0])
        self.assertNotIn('user_id',comments[0])
        self.assertEqual(warnings,[])
        page=article_page(POST,'<p>body</p>',comments)
        self.assertIn('comment is-reply',page)
        self.assertIn('↳ 답글',page)

    def test_deleted_comments_do_not_resurrect_content(self):
        comments,_=normalize_comments([{'no':1,'del_yn':'Y','memo':'deleted secret','name':'old name'}],POST,MagicMock())
        self.assertNotIn('secret',comments[0]['body_html'])
        self.assertEqual(comments[0]['author'],'삭제됨')

    def test_pending_and_genuine_zero_comments_are_different(self):
        self.assertIn('보관 대기',article_page(POST,'body',None))
        self.assertNotIn('댓글 없음',article_page(POST,'body',None))
        self.assertIn('댓글 없음',article_page(POST,'body',[]))

    def test_matches_dogdrip_twenty_row_pagination_and_search(self):
        entries=[dict(POST,id=str(i)) for i in range(1,42)]
        doc=BeautifulSoup(list_page(entries,1),'html.parser')
        self.assertEqual(len(doc.select('.post-row')),20)
        self.assertIn('archive.json?v=',str(doc))
        self.assertIn('dcinside-archive-read-posts',str(doc))
        self.assertEqual(len(BeautifulSoup(list_page(entries,3),'html.parser').select('.post-row')),1)

    def test_storage_shard_requires_sealed_owned_reference(self):
        location={'repository':'pjk3864/dcinside-archive-media-001','commit':'a'*40,'path':'assets/con.gif'}
        self.assertIn('/'+'a'*40+'/',sealed_media_url(location))
        for change in ({'commit':'main'},{'path':'assets/../secret'},{'repository':'other/private'}):
            with self.assertRaises(ValueError):
                sealed_media_url(dict(location,**change))


if __name__=='__main__':
    unittest.main()
