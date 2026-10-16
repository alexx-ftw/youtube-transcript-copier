"""Page-data-only extraction. Synthetic fixtures, no real YouTube/account data.
Every test rejects script network requests, storage writes and transcript scrolling.
"""
import json
import os
import time
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('YTCOPY_SOURCE', ROOT / 'youtube-copiar-transcripcion.user.js')).read_text(encoding='utf-8')
CSS = '''html{font-family:Arial;background:#181818;color:#eee;font-size:10px}body{margin:24px}
#actions-inner,#menu,ytd-menu-renderer{display:flex;gap:8px;justify-content:flex-end}
#menu button{font:14px Arial;color:inherit;background:#303030;border:0;border-radius:30px;height:40px;padding:0 20px}
ytd-engagement-panel-section-list-renderer{display:flex;flex-direction:column;max-width:650px;margin-top:24px;background:#242424;border:1px solid #444;border-radius:12px;overflow:hidden;font-size:16px}
#header{padding:12px}yt-section-list-renderer{display:block;height:200px;overflow:auto;padding:12px}
transcript-segment-view-model{display:block;min-height:40px}.ytwTranscriptSegmentViewModelTimestamp{display:inline;margin-right:10px}
[hidden],[visibility="ENGAGEMENT_PANEL_VISIBILITY_HIDDEN"]{display:none!important}'''
ACTIONS = '<div id="actions" class="ytd-watch-metadata"><div id="actions-inner"><div id="menu"><ytd-menu-renderer><button>Compartir</button><button>Descargar</button><button>Gracias</button></ytd-menu-renderer></div></div></div>'

def rows(n=3, word='Línea'):
    return ''.join(f'<transcript-segment-view-model><div class="ytwTranscriptSegmentViewModelTimestamp">{i//60}:{i%60:02}</div><span role="text">{word} {i}.</span></transcript-segment-view-model>' for i in range(n))

def panel(content=None, spacer=True):
    return '<ytd-engagement-panel-section-list-renderer id="panel" target-id="PAmodern_transcript_view" visibility="ENGAGEMENT_PANEL_VISIBILITY_EXPANDED"><div id="header">Transcripción</div><div id="content"><yt-section-list-renderer>'+ (rows() if content is None else content) + ('<div style="height:8000px"></div>' if spacer else '')+'</yt-section-list-renderer></div></ytd-engagement-panel-section-list-renderer>'

def cue(i, word='Línea', modern=False):
    return {'transcriptSegmentViewModel': {'startTimeMs':str(i*1000),'endTimeMs':str((i+1)*1000),'text':{'content':f'{word} {i}.'}}} if modern else {'transcriptSegmentRenderer':{'startMs':str(i*1000),'endMs':str((i+1)*1000),'snippet':{'runs':[{'text':f'{word} {i}.'}]}}}

def payload(n=20, word='Línea', modern=False):
    items=[cue(i, word, modern) for i in range(n)]
    return {'contents':[{'itemSectionRenderer':{'contents':[{'macroMarkersPanelItemViewModel':{'timelineItemViewModel':{'contentItems':[item]}}} for item in items]}}]} if modern else {'body':{'transcriptSegmentListRenderer':{'initialSegments':items}}}

class PageDataUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        args={'headless':True}
        if os.environ.get('YTCOPY_CHROMIUM'):args['executable_path']=os.environ['YTCOPY_CHROMIUM']
        cls.browser=cls.pw.chromium.launch(**args)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.pw.stop()
    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1100,'height':700},accept_downloads=True)
        self.page=self.context.new_page();self.page.set_default_timeout(2500)
        self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
    def tearDown(self):
        self.assertEqual(self.page.evaluate('window.forbidden||[]'),[])
        self.context.close();self.assertEqual(self.errors,[])
    def load(self,body=None,setup=''):
        html=f'<!doctype html><html dark><head><meta charset="utf-8"><title>Page data test - YouTube</title><style>{CSS}</style></head><body>{ACTIONS+panel() if body is None else body}</body></html>'
        self.page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
        if os.environ.get('YTCOPY_NO_NAVIGATION'):
            self.page.set_content(html)
            self.page.evaluate("window.__ytcopyLocation=new URL('http://127.0.0.1:8765/watch?v=direct01')")
        else:self.page.goto('http://127.0.0.1:8765/watch?v=direct01')
        self.page.evaluate('''() => {
          window.copied=[];window.forbidden=[];window.GM={setClipboard:async t=>window.copied.push(t)};window.unsafeWindow=window;
          window.fetch=()=>{window.forbidden.push('fetch');return Promise.reject(new Error('Network forbidden'));};
          XMLHttpRequest.prototype.open=()=>{window.forbidden.push('xhr');throw new Error('Network forbidden');};
          Storage.prototype.setItem=()=>{window.forbidden.push('storage');throw new Error('Storage forbidden');};
          window.GM_setValue=()=>window.forbidden.push('GM storage');
          window.scrolls=0;document.addEventListener('scroll',e=>{if(e.target.closest?.('ytd-engagement-panel-section-list-renderer'))window.scrolls++},true);
        }''')
        if setup:self.page.evaluate('()=>{'+setup+'}')
        code='((location)=>{\n'+SOURCE+'\n})(window.__ytcopyLocation);' if os.environ.get('YTCOPY_NO_NAVIGATION') else SOURCE
        self.page.add_script_tag(content=code)
        expect(self.page.locator('.ytcopy-copy')).to_be_visible()
        self.assertEqual(self.page.title(),'Page data test - YouTube')
    def model(self,data=None,host="document.querySelector('#panel')",prop='data'):
        return host+'.'+prop+'='+json.dumps(payload() if data is None else data)+';'
    def copy(self):self.page.locator('.ytcopy-copy').click()
    def copied(self,n=20,word='Línea',count=1):
        self.page.wait_for_function('n=>window.copied.length===n',arg=count,timeout=2500)
        self.assertEqual(self.page.evaluate('window.copied.at(-1)'),' '.join(f'{word} {i}.' for i in range(n)))
        self.assertEqual(self.page.evaluate('window.scrolls'),0)
    def review(self):
        expect(self.page.locator('.ytcopy-transcript-dialog')).to_be_visible()
        self.assertEqual(self.page.evaluate('window.copied'),[])
        self.assertEqual(self.page.evaluate('window.scrolls'),0)
    def test_01_all_backing_segments_no_scroll(self):
        self.load(setup=self.model());start=time.monotonic();self.copy();self.copied()
        self.assertLess(time.monotonic()-start,1.5)
    def test_02_modern_nested_viewmodel(self):
        self.load(setup=self.model(payload(modern=True),'document.querySelector("yt-section-list-renderer")','viewModel'));self.copy();self.copied()
    def test_03_data_without_rendered_rows(self):
        self.load(body=ACTIONS+panel(''),setup=self.model());self.copy();self.copied()
    def test_04_repeat_click_reads_new_data_not_cache(self):
        self.load(setup=self.model());self.copy();self.copied()
        self.page.evaluate('()=>{'+self.model(payload(23,word='Nueva'))+"document.querySelector('yt-section-list-renderer').innerHTML="+json.dumps(rows(word='Nueva'))+';}')
        self.copy();self.copied(23,word='Nueva',count=2)
    def test_05_idle_does_not_fetch_prefetch_or_write_storage(self):
        self.load(setup=self.model()+"window.ytInitialData={getTranscriptEndpoint:{params:'native'}};")
        self.page.wait_for_timeout(650);self.assertEqual(self.page.evaluate('window.copied'),[]);self.copy();self.copied()
    def test_06_all_static_dom_rows_read_once(self):
        self.load(body=ACTIONS+panel(rows(80),False));self.copy();self.copied(80)
    def test_07_virtual_dom_only_requires_review_without_scroll(self):
        self.load();self.copy();self.review()
    def test_08_pagination_never_silently_complete(self):
        data=payload();data['body']['transcriptSegmentListRenderer']['continuations']=[{'nextContinuationData':{'continuation':'more'}}]
        self.load(setup=self.model(data));self.copy();self.review()
        self.assertIn('Línea 19.',self.page.locator('.ytcopy-preview-text').input_value())
    def test_09_ignores_individual_row_models_as_complete_list(self):
        self.load(setup="document.querySelector('transcript-segment-view-model').data="+json.dumps(cue(0)['transcriptSegmentRenderer'])+';');self.copy();self.review()
    def test_10_wrong_language_not_merged(self):
        self.load(setup=self.model(payload(word='Different')));self.copy();self.review()
        self.assertNotIn('Different',self.page.locator('.ytcopy-preview-text').input_value())
    def test_11_malformed_cue_requires_review(self):
        data=payload();data['body']['transcriptSegmentListRenderer']['initialSegments'].append({'transcriptSegmentRenderer':{'snippet':{'simpleText':'Missing time'}}})
        self.load(setup=self.model(data));self.copy();self.review()
    def test_12_exact_repetitions_are_preserved(self):
        data=payload(1);data['body']['transcriptSegmentListRenderer']['initialSegments'].append(cue(0))
        self.load(body=ACTIONS+panel(rows(1)),setup=self.model(data));self.copy()
        self.page.wait_for_function('window.copied.length===1');self.assertEqual(self.page.evaluate('window.copied[0]'),'Línea 0. Línea 0.')
    def test_13_fractional_same_second_cues_preserved(self):
        data=payload(1);items=data['body']['transcriptSegmentListRenderer']['initialSegments'];items.append(cue(0));items[1]['transcriptSegmentRenderer']['startMs']='750'
        self.load(body=ACTIONS+panel(rows(1)),setup=self.model(data));self.copy()
        self.page.wait_for_function('window.copied.length===1');self.assertEqual(self.page.evaluate('window.copied[0]'),'Línea 0. Línea 0.')
    def test_14_3000_segments_no_proportional_render_delay(self):
        self.load(setup=self.model(payload(3000)));start=time.monotonic();self.copy();self.copied(3000);self.assertLess(time.monotonic()-start,1.5)
    def test_15_selected_tab_only(self):
        data={'tabs':[{'tabRenderer':{'selected':False,'content':payload(word='Other')}},{'tabRenderer':{'selected':True,'content':payload()}}]}
        self.load(setup=self.model(data));self.copy();self.copied()
    def test_16_language_menu_reload_not_pagination(self):
        data=payload();data['footer']={'subMenuItems':[{'selected':True,'continuation':{'reloadContinuationData':{'continuation':'es'}}},{'selected':False,'continuation':{'reloadContinuationData':{'continuation':'en'}}}]}
        self.load(setup=self.model(data));self.copy();self.copied()
    def test_17_getter_failure_no_crash_or_network(self):
        self.load(body=ACTIONS+panel(rows(),False),setup="Object.defineProperty(document.querySelector('#panel'),'data',{get(){throw new Error('sandbox')}})");self.copy();self.copied(3)
    def test_18_cycle_no_duplicate_or_hang(self):
        self.load(setup=self.model()+"document.querySelector('#panel').data.self=document.querySelector('#panel').data");self.copy();self.copied()
    def test_19_late_data_waits_without_scrolling(self):
        self.load(body=ACTIONS+panel(''));self.copy()
        self.page.evaluate('()=>{'+self.model()+'}');self.copied()
    def test_20_loading_cancel(self):
        self.load(body=ACTIONS+panel(rows()+'<div aria-busy="true">Loading</div>'),setup=self.model());self.copy()
        self.page.locator('.ytcopy-options-toggle').click();self.assertEqual(self.page.evaluate('window.copied'),[])
        expect(self.page.locator('.ytcopy-copy')).to_be_enabled();self.assertEqual(self.page.evaluate('window.scrolls'),0)
    def test_21_loading_ready_reads_latest_model(self):
        self.load(body=ACTIONS+panel(rows()+'<div aria-busy="true">Loading</div>'),setup=self.model(payload(3)));self.copy()
        self.page.evaluate('()=>{'+self.model()+"document.querySelector('#panel [aria-busy]').remove()"+'}');self.copied()
    def test_22_navigation_during_wait_never_copies(self):
        self.load(body=ACTIONS+panel(''));self.copy();self.page.evaluate("document.dispatchEvent(new Event('yt-navigate-start'))")
        expect(self.page.locator('.ytcopy-copy')).to_be_enabled();self.assertEqual(self.page.evaluate('window.copied'),[])
    def test_23_data_from_other_video_rejected(self):
        data=payload();data['videoId']='other';self.load(setup=self.model(data));self.copy();self.review()
    def test_24_models_across_hosts_not_duplicated(self):
        self.load(setup=self.model()+self.model(host="document.querySelector('yt-section-list-renderer')"));self.copy();self.copied()
    def test_25_preserves_panel_scroll_position_and_styles(self):
        self.load(setup=self.model()+"let s=document.querySelector('yt-section-list-renderer');s.scrollTop=80;s.style.scrollBehavior='smooth';window.scrolls=0")
        self.page.wait_for_timeout(100);self.page.evaluate('window.scrolls=0');self.copy();self.copied()
        self.assertEqual(self.page.locator('yt-section-list-renderer').evaluate('e=>e.scrollTop'),80)
        self.assertEqual(self.page.locator('yt-section-list-renderer').evaluate('e=>e.style.scrollBehavior'),'smooth')
    def test_26_internal_controller_data(self):
        self.load(setup=self.model({'__data':{'viewModel':payload()}},prop='polymerController'));self.copy();self.copied()
    def test_27_plain_segment_array(self):
        data={'initialSegments':[cue(i)['transcriptSegmentRenderer'] for i in range(20)]}
        self.load(setup=self.model(data));self.copy();self.copied()
    def test_28_timed_copy_uses_full_data(self):
        self.load(setup=self.model(payload(3)));self.page.locator('.ytcopy-options-toggle').click();self.page.locator('.ytcopy-options').get_by_role('button',name='Con tiempos',exact=True).click()
        self.page.wait_for_function('window.copied.length===1');self.assertEqual(self.page.evaluate('window.copied[0]'),'[0:00] Línea 0.\n[0:01] Línea 1.\n[0:02] Línea 2.')
        self.assertEqual(self.page.evaluate('window.scrolls'),0)
    def test_29_txt_uses_full_data(self):
        self.load(setup=self.model());self.page.locator('.ytcopy-options-toggle').click()
        with self.page.expect_download() as d:self.page.locator('.ytcopy-options').get_by_role('button',name='TXT',exact=True).click()
        self.assertEqual(Path(d.value.path()).read_text(encoding='utf-8'),' '.join(f'Línea {i}.' for i in range(20)))
        self.assertEqual(self.page.evaluate('window.scrolls'),0)
    def test_30_child_model_does_not_hide_parent_pagination(self):
        data=payload();data['continuations']=[{'nextContinuationData':{'continuation':'more'}}]
        self.load(setup=self.model(data)+self.model(payload(3),host="document.querySelector('yt-section-list-renderer')"));self.copy();self.review()

    def test_31_array_as_list_host_data(self):
        data=[cue(i) for i in range(20)]
        self.load(setup=self.model(data,host="document.querySelector('yt-section-list-renderer')"));self.copy();self.copied()
    def test_32_same_model_object_mutation_not_cached(self):
        self.load(setup=self.model());self.copy();self.copied()
        self.page.evaluate("document.querySelector('#panel').data.body.transcriptSegmentListRenderer.initialSegments.push("+json.dumps(cue(20))+")")
        self.copy();self.copied(21,count=2)
    def test_33_language_change_while_loading_cancels(self):
        self.load(body=ACTIONS+panel('<span data-language-code="es">Español</span>'));self.copy()
        self.page.locator('[data-language-code]').evaluate("e=>e.setAttribute('data-language-code','en')")
        expect(self.page.locator('.ytcopy-copy')).to_be_enabled();self.assertEqual(self.page.evaluate('window.copied'),[])
    def test_34_repeated_references_in_segment_array_preserved(self):
        self.load(body=ACTIONS+panel(rows(1)),setup=self.model(payload(1))+"const a=document.querySelector('#panel').data.body.transcriptSegmentListRenderer.initialSegments;a.push(a[0]);")
        self.copy();self.page.wait_for_function('window.copied.length===1');self.assertEqual(self.page.evaluate('window.copied[0]'),'Línea 0. Línea 0.')
    def test_35_parent_data_contains_child_list_once(self):
        self.load(setup=self.model()+"document.querySelector('yt-section-list-renderer').data=document.querySelector('#panel').data.body.transcriptSegmentListRenderer")
        self.copy();self.copied()
    def test_36_disagreeing_full_models_require_review(self):
        data=payload();data['body']['transcriptSegmentListRenderer']['initialSegments'][-1]=cue(19,word='Different')
        self.load(setup=self.model()+self.model(data,host="document.querySelector('yt-section-list-renderer')"));self.copy();self.review()

if __name__=='__main__':unittest.main(verbosity=2)
