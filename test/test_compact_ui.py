"""Compact toolbar regressions. Synthetic fixture; no real YouTube session.
Run with python -m unittest discover -s test -p '*_ui.py' -v.
Uses the same Playwright installation as test_mount_ui.py.
"""
import os
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

SOURCE = Path(os.environ.get('YTCOPY_SOURCE', Path(__file__).resolve().parents[1] / 'youtube-copiar-transcripcion.user.js')).read_text(encoding='utf-8')
ROWS = '''<transcript-segment-view-model><div class="ytwTranscriptSegmentViewModelTimestamp">0:00</div><span role="text">Uno de prueba.</span></transcript-segment-view-model>
<transcript-segment-view-model><div class="ytwTranscriptSegmentViewModelTimestamp">0:05</div><span role="text">Dos de prueba.</span></transcript-segment-view-model>'''
ACTIONS = '''<div id="actions" class="ytd-watch-metadata"><div id="actions-inner"><div id="menu"><ytd-menu-renderer>
<div id="top-level-buttons-computed"><button id="like">145 K</button><button id="share">Compartir</button></div>
<div id="flexible-item-buttons"><button>Descargar</button><button>Gracias</button></div><button aria-label="Más acciones">···</button>
</ytd-menu-renderer></div><div id="menu-during-ads" hidden></div></div></div>'''
PANEL = '<ytd-engagement-panel-section-list-renderer target-id="PAmodern_transcript_view" visibility="ENGAGEMENT_PANEL_VISIBILITY_EXPANDED"><div id="header"><h2>Transcripción</h2></div><div id="content"><yt-section-list-renderer>'+ROWS+'</yt-section-list-renderer></div></ytd-engagement-panel-section-list-renderer>'
CSS = '''html{font-family:Arial;background:#0f0f0f;color:#f1f1f1;font-size:10px}body{margin:24px}#actions-inner{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
#menu{min-width:0;max-width:100%}ytd-menu-renderer,#top-level-buttons-computed,#flexible-item-buttons{display:flex;gap:8px;align-items:center}
ytd-menu-renderer{flex-wrap:wrap}#menu button{height:40px;font:500 14px/20px Arial;border:0;border-radius:22px;padding:0 18px;white-space:nowrap;background:#282828;color:inherit}
ytd-engagement-panel-section-list-renderer{display:flex;flex-direction:column;max-width:600px;margin-top:24px;border:1px solid #555;border-radius:12px;overflow:hidden;background:#252525;font-size:16px}
ytd-engagement-panel-section-list-renderer>#header{padding:12px}yt-section-list-renderer{display:block;max-height:250px;overflow:auto;padding:12px}transcript-segment-view-model{display:block;margin-bottom:10px;line-height:1.5}.ytwTranscriptSegmentViewModelTimestamp{display:inline;margin-right:8px}
[hidden],[visibility="ENGAGEMENT_PANEL_VISIBILITY_HIDDEN"]{display:none!important}'''

class CompactUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        args={'headless':True}
        if os.environ.get('YTCOPY_CHROMIUM'): args['executable_path']=os.environ['YTCOPY_CHROMIUM']
        cls.browser=cls.pw.chromium.launch(**args)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1000,'height':800},accept_downloads=True)
        self.page=self.context.new_page();self.page.set_default_timeout(5000)
        self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
    def tearDown(self):
        self.context.close();self.assertEqual(self.errors,[])
    def load(self, body=ACTIONS+PANEL, setup='', dark=True, source=SOURCE):
        html=f'<!doctype html><html {"dark" if dark else ""}><head><meta charset="utf-8"><title>Compact test - YouTube</title><style>{CSS}</style></head><body>{body}</body></html>'
        self.page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
        if os.environ.get('YTCOPY_NO_NAVIGATION'):
            self.page.set_content(html)
            self.page.evaluate("window.__ytcopyLocation=new URL('http://127.0.0.1:8765/watch?v=compact-test')")
        else:
            self.page.goto('http://127.0.0.1:8765/watch?v=compact-test')
        self.page.evaluate("window.copied=[];window.GM={setClipboard:async(text)=>{window.copied.push(text)}};window.unsafeWindow=window;")
        if setup:self.page.evaluate("() => {"+setup+"}")
        code='((location)=>{\n'+source+'\n})(window.__ytcopyLocation);' if os.environ.get('YTCOPY_NO_NAVIGATION') else source
        self.page.add_script_tag(content=code)
        expect(self.bar()).to_be_visible()
        self.page.wait_for_timeout(80)
    def bar(self):return self.page.locator('#actions-inner > .ytcopy-transcript-bar')
    def copy(self):return self.bar().get_by_role('button',name='Copiar transcripción',exact=True)
    def options(self):return self.page.locator('.ytcopy-options')
    def open_options(self):
        self.bar().get_by_role('button',name='Opciones de transcripción',exact=True).click()
        expect(self.options()).to_be_visible()
    def copied(self,text='Uno de prueba. Dos de prueba.'):
        self.page.wait_for_function('window.copied.length===1',timeout=9000)
        self.assertEqual(self.page.evaluate('window.copied'),[text])
    def test_01_only_two_controls_in_action_row(self):
        self.load();self.assertEqual(self.bar().locator('button:visible').count(),2)
        expect(self.options()).not_to_be_visible()
    def test_02_native_row_alignment_not_forced_new_row(self):
        self.load();native=self.page.locator('#share').bounding_box();ours=self.copy().bounding_box()
        self.assertLess(abs(native['y']-ours['y']),1)
        self.assertEqual(native['height'],ours['height'])
    def test_03_native_tonal_button_not_white_primary(self):
        self.load();style=self.copy().evaluate('(el)=>getComputedStyle(el) .backgroundColor')
        self.assertEqual(style,'rgba(0, 0, 0, 0)')
        self.assertNotEqual(self.bar().locator('.ytcopy-compact-controls').evaluate('(el)=>getComputedStyle(el).backgroundColor'),'rgb(255, 255, 255)')
    def test_04_version_only_in_options_or_tooltip(self):
        self.load();self.assertNotIn('v1.',self.bar().inner_text())
        self.assertIn('v1.',self.copy().get_attribute('title'))
        self.open_options();expect(self.options().locator('.ytcopy-version')).to_contain_text('v1.')
    def test_05_options_without_clipboard_side_effect(self):
        self.load();self.open_options()
        self.assertEqual(self.page.evaluate('window.copied'),[])
        for n in ['Con tiempos','Ver texto','TXT']:expect(self.options().get_by_role('button',name=n,exact=True)).to_be_visible()
    def test_06_escape_closes_and_restores_focus(self):
        self.load();self.open_options();self.page.keyboard.press('Escape')
        expect(self.options()).not_to_be_visible()
        expect(self.bar().get_by_role('button',name='Opciones de transcripción')).to_be_focused()
    def test_07_outside_click_closes_preserves_native_handler(self):
        self.load(setup="window.shares=0;document.querySelector('#share').onclick=()=>window.shares++")
        self.assertEqual(self.page.evaluate('window.shares'),0)
        self.open_options();self.page.locator('#share').click()
        expect(self.options()).not_to_be_visible();self.assertEqual(self.page.evaluate('window.shares'),1)
    def test_08_direct_copy_and_feedback(self):
        self.load();self.copy().click();self.copied()
        expect(self.bar()).to_have_attribute('data-state','success')
        expect(self.bar().locator('.ytcopy-copy-label')).to_have_text('Copiado')
        self.page.wait_for_timeout(2500)
        expect(self.bar().locator('.ytcopy-copy-label')).to_have_text('Copiar')
    def test_09_timed_copy_from_options(self):
        self.load();self.open_options();self.options().get_by_role('button',name='Con tiempos',exact=True).click()
        expect(self.options()).not_to_be_visible();self.copied('[0:00] Uno de prueba.\n[0:05] Dos de prueba.')
    def test_10_preview_and_format_buttons(self):
        self.load();self.open_options();self.options().get_by_role('button',name='Ver texto',exact=True).click()
        text=self.page.locator('.ytcopy-preview-text');expect(text).to_have_value('Uno de prueba. Dos de prueba.',timeout=9000)
        self.assertEqual(self.page.evaluate('window.copied'),[])
        self.page.locator('.ytcopy-modes').get_by_role('button',name='Con tiempos',exact=True).click()
        expect(text).to_have_value('[0:00] Uno de prueba.\n[0:05] Dos de prueba.')
        self.page.get_by_role('button',name='Cerrar vista previa').click()
        expect(self.copy()).to_be_focused()
    def test_11_txt_from_options(self):
        self.load();self.open_options()
        with self.page.expect_download(timeout=9000) as d:self.options().get_by_role('button',name='TXT',exact=True).click()
        self.assertEqual(Path(d.value.path()).read_text(encoding='utf-8'),'Uno de prueba. Dos de prueba.')
    def test_12_busy_cancel_without_expanding_toolbar(self):
        self.load(body=ACTIONS);before=self.bar().bounding_box();self.copy().click()
        expect(self.bar().get_by_role('button',name='Cancelar',exact=True)).to_be_visible()
        self.assertEqual(self.bar().bounding_box()['height'],before['height'])
        self.bar().get_by_role('button',name='Cancelar',exact=True).click()
        expect(self.bar()).to_have_attribute('aria-busy','false')
        self.assertEqual(self.page.evaluate('window.copied'),[])
    def test_13_narrow_auto_icon_does_not_move_native_buttons(self):
        self.load();width=self.page.locator('#menu').bounding_box()['width']
        self.page.locator('#actions-inner').evaluate('(el,w)=>el.style.width=`${w+84}px`',width)
        expect(self.bar()).to_have_attribute('data-compact','true')
        self.assertLess(abs(self.page.locator('#share').bounding_box()['y']-self.copy().bounding_box()['y']),1)
        expect(self.bar().locator('.ytcopy-copy-label')).not_to_be_visible()
    def test_14_resize_restores_label(self):
        self.load();self.page.locator('#actions-inner').evaluate("el=>el.style.width='550px'")
        expect(self.bar()).to_have_attribute('data-compact','true')
        self.page.locator('#actions-inner').evaluate("el=>el.style.width='900px'")
        expect(self.bar()).to_have_attribute('data-compact','false')
        expect(self.bar().locator('.ytcopy-copy-label')).to_be_visible()
    def test_15_320px_options_fit_and_buttons_reachable(self):
        self.page.set_viewport_size({'width':320,'height':660});self.load();self.open_options()
        box=self.options().bounding_box();self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],320)
        self.assertLessEqual(box['y']+box['height'],660)
        for n in ['Con tiempos','Ver texto','TXT']:expect(self.options().get_by_role('button',name=n,exact=True)).to_be_visible()
    def test_16_light_theme(self):
        self.load(dark=False);self.open_options()
        self.assertEqual(self.options().evaluate('el=>getComputedStyle(el).backgroundColor'),'rgb(255, 255, 255)')
        self.assertEqual(self.options().evaluate('el=>getComputedStyle(el).color'),'rgb(23, 23, 23)')
    def test_17_rebuild_cleans_popover_and_duplicate_listeners(self):
        self.load();self.open_options();self.bar().evaluate('el=>el.remove()')
        expect(self.bar()).to_have_count(1);expect(self.options()).not_to_be_visible()
        self.open_options();expect(self.options()).to_have_count(1)
        self.page.locator('#share').click();expect(self.options()).not_to_be_visible()
    def test_18_navigation_closes_options(self):
        self.load();self.open_options();self.page.evaluate("document.dispatchEvent(new Event('yt-navigate-start'))")
        expect(self.options()).not_to_be_visible()
    def test_19_keyboard_open_and_tab_navigation(self):
        self.load();self.bar().get_by_role('button',name='Opciones de transcripción').focus();self.page.keyboard.press('Enter')
        expect(self.options().get_by_role('button',name='Con tiempos',exact=True)).to_be_focused()
        self.page.keyboard.press('Tab');expect(self.options().get_by_role('button',name='Ver texto',exact=True)).to_be_focused()
    def test_20_clipboard_error_keeps_preview_and_no_false_success(self):
        self.load(setup="window.GM={setClipboard:async()=>{throw new Error('blocked')}};Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw new Error('blocked')}}});")
        self.copy().click();expect(self.page.locator('.ytcopy-preview-text')).to_have_value('Uno de prueba. Dos de prueba.',timeout=9000)
        expect(self.bar()).to_have_attribute('data-state','warning')
        self.assertEqual(self.page.evaluate('window.copied'),[])
        expect(self.page.locator('.ytcopy-transcript-dialog .ytcopy-status')).to_contain_text('No se pudo confirmar')
    def test_21_error_shown_in_notice_not_layout_row(self):
        self.load(body=ACTIONS+PANEL.replace(ROWS,'<textarea aria-label="Buscar en transcripción">Uno</textarea>'+ROWS))
        before=self.bar().bounding_box();self.copy().click()
        expect(self.page.locator('.ytcopy-toast')).to_contain_text('Borra la búsqueda')
        self.assertEqual(self.bar().bounding_box()['height'],before['height'])
        self.page.get_by_role('button',name='Cerrar aviso').click();expect(self.page.locator('.ytcopy-toast')).to_have_count(0)
    def test_22_portal_not_clipped_by_parent(self):
        self.load();self.page.locator('#actions-inner').evaluate("el=>{el.style.overflow='hidden';el.style.height='40px';}")
        self.open_options();btn=self.options().get_by_role('button',name='Ver texto',exact=True)
        box=btn.bounding_box();self.assertTrue(btn.evaluate('(el)=>{let r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}'))
    def test_23_reduced_motion_disables_spinner_animation(self):
        self.page.emulate_media(reduced_motion='reduce');self.load(body=ACTIONS);self.copy().click()
        self.assertEqual(self.bar().locator('.ytcopy-copy-icon').evaluate('el=>getComputedStyle(el).animationName'),'none')
        self.page.keyboard.press('Escape')
    def test_24_options_fallback_without_popover_API(self):
        self.load(setup="HTMLElement.prototype.showPopover=undefined;");self.open_options()
        self.assertFalse(self.options().get_attribute('popover'))
        self.page.keyboard.press('Escape');expect(self.options()).not_to_be_visible()
    def test_25_scroll_repositions_options(self):
        self.load(body=ACTIONS+PANEL+'<div style="height:1500px"></div>');self.open_options()
        old=self.options().bounding_box()['y'];self.page.evaluate('window.scrollTo(0,20)');self.page.wait_for_timeout(100)
        self.assertNotEqual(self.options().bounding_box()['y'],old)
    def test_26_native_menu_is_not_rewritten(self):
        self.load();self.assertEqual(self.page.locator('#menu button').all_text_contents(),['145 K','Compartir','Descargar','Gracias','···'])
        self.assertEqual(self.page.locator('#menu .ytcopy-transcript-bar').count(),0)
    def test_27_single_options_panel_across_repeated_open_close(self):
        self.load()
        for _ in range(3):self.open_options();self.page.keyboard.press('Escape')
        expect(self.options()).to_have_count(1)
    def test_28_sidebar_copy_not_broken(self):
        self.load();self.page.locator('ytd-engagement-panel-section-list-renderer .ytcopy-transcript-bar').get_by_role('button',name='Copiar texto',exact=True).click();self.copied()
    def test_29_long_video_warning_not_auto_copied(self):
        self.load(body=ACTIONS+PANEL.replace('0:05','15:00'));self.copy().click()
        expect(self.page.locator('.ytcopy-transcript-dialog')).to_be_visible(timeout=9000)
        self.assertEqual(self.page.evaluate('window.copied'),[])
        expect(self.bar()).to_have_attribute('data-state','warning')
    def test_30_no_context_stale_on_navigation(self):
        self.load(body=ACTIONS);self.copy().click();self.page.evaluate("document.dispatchEvent(new Event('yt-navigate-start'));(window.__ytcopyLocation ? window.__ytcopyLocation.href='http://127.0.0.1:8765/watch?v=next-video' : history.pushState({},'', '/watch?v=next-video'))")
        expect(self.bar()).to_have_attribute('aria-busy','false');self.assertEqual(self.page.evaluate('window.copied'),[])
        expect(self.page.locator('.ytcopy-toast')).to_have_count(0)

if __name__=='__main__':unittest.main(verbosity=2)
