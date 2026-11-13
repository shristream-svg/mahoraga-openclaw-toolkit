"""Optional pypdf tests; all source/output files are synthetic temporary fixtures."""
import hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
if importlib.util.find_spec('pypdf') is None:raise unittest.SkipTest('Optional pypdf dependency is not installed')
from pypdf import PdfReader,PdfWriter
ROOT=Path(__file__).resolve().parents[1]
ENV={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','SYSTEMDRIVE','PATH','TEMP','TMP','COMSPEC','PATHEXT')};ENV['PYTHONUTF8']='1'
class FileTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def run_tool(self,*args,ok=True):
        r=subprocess.run([sys.executable,'-m','mahoraga_toolkit.file_tools',*map(str,args)],cwd=str(ROOT),env=ENV,capture_output=True,text=True,encoding='utf-8',timeout=8)
        self.assertEqual(r.returncode==0,ok,(r.stdout,r.stderr));return json.loads(r.stdout if ok else r.stderr)
    def pdf(self,name,pages):
        p=self.root/name;w=PdfWriter()
        for _ in range(pages):w.add_blank_page(width=200,height=200)
        with p.open('wb') as f:w.write(f)
        return p
    def test_exclusive_copy_matches_independent_hash_and_preserves_source(self):
        source=self.root/'source.bin';dest=self.root/'copy.bin';source.write_bytes(b'SYNTHETIC\x00FILE')
        r=self.run_tool('copy-verified',source,dest)
        self.assertEqual(source.read_bytes(),dest.read_bytes());self.assertEqual(r['sha256'],hashlib.sha256(dest.read_bytes()).hexdigest())
    def test_copy_refuses_overwriting_existing_file(self):
        source=self.root/'source';dest=self.root/'dest';source.write_bytes(b'NEW');dest.write_bytes(b'PROTECTED')
        self.run_tool('copy-verified',source,dest,ok=False);self.assertEqual(dest.read_bytes(),b'PROTECTED')
    def test_quoted_csv_exact_decimal_total_and_readback(self):
        source=self.root/'sales.csv';out=self.root/'total.json';source.write_text('label,amount\n"print, color",120.25\nscan,79.75\nforms,300\n',encoding='utf-8-sig')
        r=self.run_tool('csv-total',source,'amount',out);self.assertEqual(r['total'],500);self.assertEqual(r['totalExact'],'500.00');self.assertEqual(r['rows'],3);self.assertEqual(json.loads(out.read_text()),r)
    def test_csv_refuses_existing_output_and_nonfinite_values(self):
        source=self.root/'bad.csv';out=self.root/'out.json';source.write_text('amount\nNaN\n');out.write_bytes(b'PROTECTED')
        self.run_tool('csv-total',source,'amount',out,ok=False);self.assertEqual(out.read_bytes(),b'PROTECTED')
        absent=self.root/'not-created.json';self.run_tool('csv-total',source,'amount',absent,ok=False);self.assertFalse(absent.exists())
    def test_pdf_information_counts_actual_pages(self):
        r=self.run_tool('pdf-info',self.pdf('two.pdf',2));self.assertEqual(r['page_count'],2);self.assertEqual(r['text_char_count'],0)
    def test_pdf_merge_has_independent_page_readback(self):
        first=self.pdf('one.pdf',1);second=self.pdf('two.pdf',2);out=self.root/'merged.pdf'
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (first,second)]
        r=self.run_tool('pdf-merge',out,first,second);self.assertEqual(r['page_count'],3);self.assertEqual(len(PdfReader(out).pages),3)
        self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (first,second)])
    def test_pdf_merge_refuses_existing_output(self):
        source=self.pdf('one.pdf',1);out=self.root/'existing.pdf';out.write_bytes(b'PROTECTED')
        self.run_tool('pdf-merge',out,source,ok=False);self.assertEqual(out.read_bytes(),b'PROTECTED')
    def test_blank_pdf_extraction_reports_empty_text_honestly(self):
        source=self.pdf('blank.pdf',1);out=self.root/'text.txt';r=self.run_tool('pdf-text',source,out)
        self.assertEqual(r['chars'],0);self.assertEqual(out.read_bytes(),b'')
