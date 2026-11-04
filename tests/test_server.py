import json
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from pypdf import PdfReader

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        server.DATA=Path(self.temp.name)
        fixture = json.loads((Path(__file__).parent / 'fixtures' / 'profile.json').read_text())
        self.seed_patch = patch.object(server, 'seed_profile', return_value=fixture)
        self.seed_patch.start()
        self.addCleanup(self.seed_patch.stop)
        server.initialize()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        server.PORT=self.http.server_address[1]
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{server.PORT}/api/'
        with server.db() as con:
            con.execute('DELETE FROM sources')
        self.job={'title':'Software Engineering Intern','company':'Test Company','url':'https://jobs.lever.co/test/123','location':'Remote','description':'Python, SQL, React and Kubernetes. Undergraduate internships.'}
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.temp.cleanup()
    def call(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        with urllib.request.urlopen(req) as r:return json.load(r)
    def draft(self):
        j=self.call('job',self.job)
        return self.call('prepare',{'job_id':j['id']})['id']
    def app(self,aid):return next(a for a in self.call('state')['applications'] if a['id']==aid)
    def test_review_gate_snapshot_and_edit_revocation(self):
        aid=self.draft()
        headers={'Authorization':'Bearer '+server.TOKEN}
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.call(f'extension/application/{aid}',headers=headers)
        self.assertEqual(ctx.exception.code,400)
        self.call('application',{'id':aid,'action':'approve','reviewed':True})
        approved=self.call(f'extension/application/{aid}',headers=headers)
        profile=self.call('state')['profile'];profile['email']='changed@example.com'
        self.call('profile',profile)
        self.assertEqual(self.call(f'extension/application/{aid}',headers=headers)['fields']['email'],approved['fields']['email'])
        self.call('application',{'id':aid,'action':'save','resume':'Edited resume','fields':approved['fields']})
        self.assertEqual(self.app(aid)['status'],'draft')
        with self.assertRaises(urllib.error.HTTPError):self.call(f'extension/application/{aid}',headers=headers)
    def test_duplicate_and_no_fabrication(self):
        aid=self.draft();app=self.app(aid)
        j=self.call('state')['jobs'][0]
        self.assertEqual(self.call('prepare',{'job_id':j['id']})['id'],aid)
        self.assertEqual(sorted(app['resume'].splitlines()),sorted(app['profile_snapshot']['resume'].splitlines()))
        self.assertTrue(app['resume'].startswith('Alex Example'))
        self.assertNotIn('kubernetes',app['resume'].lower())
        self.assertNotIn('sponsorship',app['fields'])
    def test_untrusted_origin_and_extension_token(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.call('profile',{},headers={'Origin':'https://evil.example'})
        self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError):self.call('extension/applications')
        with self.assertRaises(urllib.error.HTTPError):self.call('state',headers={'Host':'evil.example'})
    def test_monitor_dedup_close_reopen_and_failed_feed(self):
        self.call('source',{'provider':'lever','slug':'test','company':'Test'})
        fixture={'external_id':'123','title':'Software Engineering Intern','location':'Remote','url':self.job['url'],'description':self.job['description']}
        with patch.object(server,'fetch_source',return_value=[fixture]),patch.object(server,'notify_desktop'):
            self.assertEqual(server.poll_sources()['new'],1)
            self.assertEqual(server.poll_sources()['new'],0)
        aid=self.call('prepare',{'job_id':self.call('state')['jobs'][0]['id']})['id']
        self.call('application',{'id':aid,'action':'approve','reviewed':True})
        with patch.object(server,'fetch_source',side_effect=TimeoutError('timeout')):
            self.assertEqual(len(server.poll_sources()['errors']),1)
            self.assertEqual(self.call('state')['jobs'][0]['open'],1)
        with patch.object(server,'fetch_source',return_value=[]):server.poll_sources()
        with self.assertRaises(urllib.error.HTTPError):self.call(f'extension/application/{aid}',headers={'Authorization':'Bearer '+server.TOKEN})
        fixture['description']='Changed Python requirements'
        with patch.object(server,'fetch_source',return_value=[fixture]):server.poll_sources()
        self.assertEqual(self.call('state')['jobs'][0]['open'],1)
        self.assertEqual(self.app(aid)['status'],'draft')
    def test_relevance_and_validation(self):
        p=server.seed_profile()
        for title in ['Software Engineer Intern','AI Intern','Data Science Intern','Cloud Engineering Co-op','Research Internship']:
            self.assertTrue(server.relevant({'title':title,'location':'Anywhere'},p),title)
        for title in ['Senior Software Engineer','International Sales Director','Paid Marketing Intern', 'Staff Software Engineer - Database Engine Internals', 'Senior Software Engineer, Internal Fraud Platform', 'Engineering Manager, Agentic Internet & Data Insights']:
            self.assertFalse(server.relevant({'title':title,'location':'Anywhere'},p),title)
        with self.assertRaises(urllib.error.HTTPError):self.call('job',{**self.job,'url':'javascript:alert(1)'})
    def test_pdf_preserves_facts(self):
        aid=self.draft();text=self.app(aid)['resume']
        pdf=server.make_pdf(text);reader=PdfReader(BytesIO(pdf))
        extracted=' '.join(p.extract_text() for p in reader.pages)
        for phrase in ['Alex Example','Example University','92%','42 samples','Example Lab']:
            self.assertIn(phrase,extracted)
        self.assertLessEqual(len(reader.pages),2)
    def test_ashby_adapter_and_auto_prepare(self):
        fixture={'jobs':[{'id':'ashby-1','title':'AI Intern','location':'NYC','isRemote':True,'isListed':True,'applyUrl':'https://jobs.ashbyhq.com/test/ashby-1/application','descriptionPlain':'Python intern role'}]}
        with patch.object(server,'download_json',return_value=fixture):
            rows=server.fetch_source({'provider':'ashby','slug':'test'})
        self.assertEqual(rows[0]['external_id'],'ashby-1')
        self.assertIn('Remote',rows[0]['location'])
        self.call('source',{'provider':'ashby','slug':'test','company':'Test'})
        with patch.object(server,'fetch_source',return_value=rows),patch.object(server,'notify_desktop'):
            server.poll_sources()
        self.assertEqual(len(self.call('state')['applications']),1)
        self.assertEqual(self.call('state')['applications'][0]['status'],'draft')

    def test_submitted_state_requires_approval(self):
        aid=self.draft()
        with self.assertRaises(urllib.error.HTTPError):self.call('application',{'id':aid,'action':'submitted'})
        self.call('application',{'id':aid,'action':'approve','reviewed':True})
        self.call('application',{'id':aid,'action':'submitted'})
        self.assertEqual(self.app(aid)['status'],'submitted')
        self.assertEqual(self.call('extension/applications',headers={'Authorization':'Bearer '+server.TOKEN}),[])

if __name__=='__main__':unittest.main()
