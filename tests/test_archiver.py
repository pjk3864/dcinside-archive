import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
import archiver as a


class ArchiveTests(unittest.TestCase):
    def test_octet_stream_image_is_saved(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.headers = {'Content-Type':'application/octet-stream'}
        response.iter_content.return_value = [b'\xff\xd8\xffexample']
        s = MagicMock()
        s.get.return_value.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as tmp, patch.object(a,'ROOT',Path(tmp)):
            warnings = []
            path = a.media(s,'https://dcimg6.dcinside.co.kr/viewimage.php','1','https://gall.dcinside.com/',warnings)
            self.assertTrue(path.endswith('.jpg'))
            self.assertTrue((Path(tmp)/path[3:]).is_file())
            self.assertEqual(warnings,[])

    def test_list_skips_notice(self):
        doc = BeautifulSoup('<tr class="ub-content" data-no="9"><td class="gall_num">공지</td><td class="gall_tit"><a href="/board/view/?no=9">notice</a></td></tr><tr class="ub-content" data-no="10"><td class="gall_num">10</td><td class="gall_tit"><a href="/board/view/?no=10"><div class="thumimg">thumbnail</div>title</a></td></tr>','html.parser')
        posts = a.parse_list(doc)
        self.assertEqual([p['id'] for p in posts],['10'])
        self.assertEqual(posts[0]['title'],'title')

    def test_empty_list_is_failure(self):
        with self.assertRaises(RuntimeError):
            a.parse_list(BeautifulSoup('<html></html>','html.parser'))

    def test_post_sanitizes_scripts_and_events(self):
        doc = BeautifulSoup('<span class="title_subject">safe</span><div class="write_div"><script>alert(1)</script><p onclick="bad()">hello</p><a href="javascript:bad()">link</a></div>','html.parser')
        with tempfile.TemporaryDirectory() as tmp, patch.object(a,'ROOT',Path(tmp)), patch.object(a,'document',return_value=doc):
            entry = a.archive_post(None,{'id':'1','source_url':'https://gall.dcinside.com/board/view/?id=dcbest&no=1'})
            text = (Path(tmp)/'posts/1.html').read_text(encoding='utf-8')
            self.assertNotIn('onclick',text)
            self.assertNotIn('javascript:',text)
            self.assertNotIn('alert(1)',text)
            self.assertEqual(entry['title'],'safe')

    def test_partial_failure_saves_success_and_queue(self):
        posts = [{'id':'2','title':'ok','source_url':'https://gall.dcinside.com/'},{'id':'1','title':'bad','source_url':'https://gall.dcinside.com/'}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(a,'ROOT',Path(tmp)), patch.object(a,'session'), patch.object(a,'document'), patch.object(a,'parse_list',return_value=posts), patch.object(a,'archive_post',side_effect=[dict(posts[0],published='',archived_at=a.now()),RuntimeError('temporary')]), patch.object(a.time,'sleep'):
            with self.assertRaises(RuntimeError):
                a.collect(pages=1)
            self.assertEqual([p['id'] for p in a.load('archive.json',[])],['2'])
            self.assertEqual([p['id'] for p in a.load('pending.json',[])],['1'])
            self.assertTrue((Path(tmp)/'index.html').exists())

    def test_old_pending_post_is_retried(self):
        old = {'id':'1','title':'retry','source_url':'https://gall.dcinside.com/'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(a,'ROOT',Path(tmp)), patch.object(a,'session'), patch.object(a,'document'), patch.object(a,'parse_list',return_value=[{'id':'3','title':'known'}]), patch.object(a,'archive_post',return_value=dict(old,published='')) as archive, patch.object(a.time,'sleep'):
            a.save('state.json',{'initialized':True,'last_seen_id':3})
            a.save('archive.json',[{'id':'3','title':'known'}])
            a.save('pending.json',[old])
            a.collect()
            self.assertEqual(archive.call_args.args[1]['id'],'1')
            self.assertEqual(a.load('pending.json',[]),[])


if __name__ == '__main__':
    unittest.main()
