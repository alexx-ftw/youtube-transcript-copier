"""UI regressions for action toolbar + combined YouTube transcript panels.
Run: python3 -m unittest discover -s test -p '*_ui.py' -v
Dependencies: python3 -m pip install -r test/requirements-ui.txt
Browser: python3 -m playwright install chromium
Optional: YTCOPY_SOURCE and YTCOPY_CHROMIUM (absolute paths).
YTCOPY_NO_NAVIGATION=1 renders offline on about:blank with a simulated URL;
the default CI path uses an actual localhost URL and unmodified injection.
Fixtures are synthetic and contain no uploaded user/page data.
"""
from pathlib import Path
import os
import unittest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('YTCOPY_SOURCE', ROOT / 'youtube-copiar-transcripcion.user.js')).read_text()
ACTIONS = '''<div id="actions" class="item style-scope ytd-watch-metadata"><div id="actions-inner">
<div id="menu"><ytd-menu-renderer><div id="top-level-buttons-computed"><button id="share">Compartir</button></div>
<div id="flexible-item-buttons"><button>Descargar</button><button>Gracias</button></div><button>Más acciones</button>
</ytd-menu-renderer></div><div id="menu-during-ads" hidden></div></div></div>'''
ROWS = '''<transcript-segment-view-model><div class="ytwTranscriptSegmentViewModelTimestamp" aria-hidden="true">0:00</div>
<div class="ytwTranscriptSegmentViewModelTimestampA11yLabel">0 segundos</div><span role="text">Inicio de prueba.</span></transcript-segment-view-model>
<transcript-segment-view-model><div class="ytwTranscriptSegmentViewModelTimestamp" aria-hidden="true">0:05</div>
<div class="ytwTranscriptSegmentViewModelTimestampA11yLabel">5 segundos</div><span role="text">Fin de prueba.</span></transcript-segment-view-model>'''
TABS = '''<div id="subheader"><div role="tablist"><button id="chapters" role="tab" aria-selected="false">Capítulos</button>
<button id="transcript-tab" role="tab" aria-label="Transcripción" aria-selected="true">Transcripción</button></div></div>'''
CSS = '''html{font-family:Arial;font-size:10px;background:#0f0f0f;color:#eee}body{margin:12px}button{font:14px Arial;padding:10px;border:0;border-radius:22px}
ytd-watch-metadata{display:block;min-width:0}#actions-inner,ytd-menu-renderer,#top-level-buttons-computed,#flexible-item-buttons{display:flex;gap:8px;align-items:center}
#actions-inner{justify-content:flex-end}#menu{min-width:0}ytd-engagement-panel-section-list-renderer{display:flex;flex-direction:column;margin-top:16px;border:1px solid #555;border-radius:12px;overflow:hidden;width:min(650px,100%);font-size:16px;background:#252525}
ytd-engagement-panel-section-list-renderer>[id=header]{padding:14px}yt-section-list-renderer{display:block;max-height:220px;overflow:auto;padding:12px}
transcript-segment-view-model,ytd-transcript-segment-renderer{display:block;line-height:1.6;margin:10px 0}.ytwTranscriptSegmentViewModelTimestamp{display:inline-block;margin-right:10px}
.ytwTranscriptSegmentViewModelTimestampA11yLabel{position:absolute;clip:rect(0,0,0,0);width:1px;height:1px;overflow:hidden}
[hidden],[visibility="ENGAGEMENT_PANEL_VISIBILITY_HIDDEN"]{display:none!important}'''


def panel(rows=ROWS, target='', tabs=True, hidden=False, ident='test-panel'):
    return f'''<ytd-engagement-panel-section-list-renderer id="{ident}" {f'target-id="{target}"' if target else ''}
visibility="ENGAGEMENT_PANEL_VISIBILITY_{'HIDDEN' if hidden else 'EXPANDED'}"><div id="header"><h2>En este vídeo</h2>{TABS if tabs else ''}</div>
<div id="content"><yt-section-list-renderer>{rows}</yt-section-list-renderer></div><div id="footer"></div></ytd-engagement-panel-section-list-renderer>'''


class MountUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        opts = {'headless': True}
        if os.environ.get('YTCOPY_CHROMIUM'):
            opts['executable_path'] = os.environ['YTCOPY_CHROMIUM']
        cls.browser = cls.pw.chromium.launch(**opts)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1100, 'height': 800}, accept_downloads=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(6000)
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def load(self, body, setup='', path='/watch?v=testvideo01'):
        html = f'<!DOCTYPE html><html dark><head><meta charset="utf-8"><title>Prueba de transcripción - YouTube</title><style>{CSS}</style></head><body>{body}</body></html>'
        self.page.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
        if os.environ.get('YTCOPY_NO_NAVIGATION'):
            self.page.set_content(html)
            self.page.evaluate('(path)=>{window.__ytcopyLocation=new URL("http://127.0.0.1:8765"+path)}', path)
        else:
            self.page.goto('http://127.0.0.1:8765' + path)
        self.assertEqual(self.page.evaluate('document.characterSet'), 'UTF-8')
        self.page.evaluate('window.copied=[]; window.GM={setClipboard:async text=>{window.copied.push(text)}}; window.unsafeWindow=window;')
        if setup:
            self.page.evaluate(setup)
        code = '((location)=>{\n' + SOURCE + '\n})(window.__ytcopyLocation);' if os.environ.get('YTCOPY_NO_NAVIGATION') else SOURCE
        self.page.add_script_tag(content=code)
        self.assertIn('YouTube', self.page.title())
        self.assertEqual(self.page.locator('body').count(), 1)

    def actionbar(self):
        return self.page.locator('#actions-inner > .ytcopy-transcript-bar')

    def advanced(self, name):
        self.actionbar().get_by_role('button', name='Opciones de transcripción', exact=True).click()
        return self.page.locator('.ytcopy-options').get_by_role('button', name=name, exact=True)

    def sidebar(self):
        return self.page.locator('#test-panel > .ytcopy-transcript-bar')

    def copied(self, text):
        expect(self.page.locator('.ytcopy-status').filter(has_text='Copiado').first).to_be_visible(timeout=9000)
        self.assertEqual(self.page.evaluate('window.copied'), [text])

    def test_01_actions_exist_without_open_panel(self):
        self.load(ACTIONS)
        expect(self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True)).to_be_visible()
        expect(self.page.locator('.ytcopy-options')).not_to_be_visible()
        self.actionbar().get_by_role('button', name='Opciones de transcripción', exact=True).click()
        expect(self.page.locator('.ytcopy-options').get_by_role('button', name='Con tiempos', exact=True)).to_be_visible()
        expect(self.page.locator('#share')).to_be_visible()

    def test_02_combined_panel_without_target_is_detected(self):
        self.load(panel())
        expect(self.sidebar().get_by_role('button', name='Copiar texto', exact=True)).to_be_visible()

    def test_03_combined_panel_unknown_target_is_detected(self):
        self.load(panel(target='combined-chapters-and-transcript'))
        expect(self.sidebar()).to_be_visible()

    def test_04_rows_added_to_existing_unknown_root(self):
        self.load(panel(rows='', tabs=False))
        self.page.locator('#test-panel yt-section-list-renderer').evaluate('(el, html) => el.innerHTML=html', ROWS)
        expect(self.sidebar()).to_be_visible()

    def test_05_actions_added_after_script_started(self):
        self.load('<main id="late"></main>')
        self.page.locator('#late').evaluate('(el,html)=>el.innerHTML=html', ACTIONS)
        expect(self.actionbar()).to_be_visible()

    def test_06_recovers_removed_actionbar_without_duplicates(self):
        self.load(ACTIONS + panel())
        expect(self.actionbar()).to_be_visible()
        self.actionbar().evaluate('(el)=>el.remove()')
        expect(self.actionbar()).to_be_visible()
        self.page.evaluate('for(let i=0;i<5;i++)document.dispatchEvent(new Event("yt-navigate-finish"))')
        self.page.wait_for_timeout(300)
        expect(self.actionbar()).to_have_count(1)
        expect(self.sidebar()).to_have_count(1)

    def test_07_copy_uses_visible_combined_not_hidden_legacy(self):
        stale = panel(rows=ROWS.replace('prueba', 'OBSOLETO'), target='PAmodern_transcript_view', tabs=False, hidden=True, ident='stale')
        self.load(ACTIONS + stale + panel())
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba.')

    def test_08_open_native_transcript_then_copy(self):
        self.load(ACTIONS + '<ytd-video-description-transcript-section-renderer><button id="opener">Mostrar transcripción</button></ytd-video-description-transcript-section-renderer>' + panel(hidden=True),
            '() => {document.querySelector("#opener").onclick=()=>document.querySelector("#test-panel").setAttribute("visibility","ENGAGEMENT_PANEL_VISIBILITY_EXPANDED");}')
        expect(self.page.locator('#test-panel')).not_to_be_visible()
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba.')

    def test_09_select_transcript_tab_before_reading(self):
        self.load(ACTIONS + panel(rows=''), '''() => {
            document.querySelector('#transcript-tab').setAttribute('aria-selected','false');
            document.querySelector('#chapters').setAttribute('aria-selected','true');
            document.querySelector('#transcript-tab').onclick=()=>{
              document.querySelector('#chapters').setAttribute('aria-selected','false');
              document.querySelector('#transcript-tab').setAttribute('aria-selected','true');
              document.querySelector('yt-section-list-renderer').innerHTML=''' + repr(ROWS) + ''';
            };
        }''')
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba.')
        expect(self.page.locator('#transcript-tab')).to_have_attribute('aria-selected', 'true')

    def test_10_cancel_while_waiting_for_panel(self):
        self.load(ACTIONS)
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.actionbar().get_by_role('button', name='Cancelar', exact=True).click()
        expect(self.actionbar().locator('.ytcopy-status')).to_contain_text('cancelada')
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_11_navigation_while_opening_cancels(self):
        self.load(ACTIONS)
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.page.evaluate('document.dispatchEvent(new Event("yt-navigate-start"));(window.__ytcopyLocation ? window.__ytcopyLocation.href="http://127.0.0.1:8765/watch?v=newvideo02" : history.pushState({},"","/watch?v=newvideo02"))')
        expect(self.actionbar().locator('.ytcopy-status')).to_contain_text('cambiado')
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_12_filter_never_copies_partial_matches(self):
        self.load(ACTIONS + panel(rows='<textarea aria-label="Buscar en transcripción">prueba</textarea>' + ROWS))
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        expect(self.actionbar().locator('.ytcopy-status')).to_contain_text('Borra la búsqueda')
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_13_time_format(self):
        self.load(ACTIONS + panel())
        self.advanced('Con tiempos').click()
        self.copied('[0:00] Inicio de prueba.\n[0:05] Fin de prueba.')

    def test_14_preview_without_clipboard_side_effect(self):
        self.load(ACTIONS + panel())
        self.advanced('Ver texto').click()
        expect(self.page.locator('.ytcopy-preview-text')).to_have_value('Inicio de prueba. Fin de prueba.', timeout=9000)
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_15_txt_download(self):
        self.load(ACTIONS + panel())
        with self.page.expect_download(timeout=9000) as info:
            self.advanced('TXT').click()
        self.assertEqual(Path(info.value.path()).read_text(), 'Inicio de prueba. Fin de prueba.')
        self.assertTrue(info.value.suggested_filename.endswith('.txt'))

    def test_16_old_panel_still_works(self):
        self.load(panel(target='engagement-panel-searchable-transcript', tabs=False))
        self.sidebar().get_by_role('button', name='Copiar texto', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba.')

    def test_17_small_viewport_toolbar_not_clipped(self):
        self.page.set_viewport_size({'width':320,'height':800})
        self.load(ACTIONS + panel())
        expect(self.actionbar()).to_be_visible()
        for name in ['Copiar transcripción', 'Opciones de transcripción']:
            btn = self.actionbar().get_by_role('button',name=name,exact=True)
            expect(btn).to_be_visible()
            box = btn.bounding_box()
            self.assertGreaterEqual(box['x'], 0)
            self.assertLessEqual(box['x'] + box['width'], 321)
        self.actionbar().get_by_role('button', name='Opciones de transcripción').click()
        for name in ['Con tiempos', 'Ver texto', 'TXT']:
            btn = self.page.locator('.ytcopy-options').get_by_role('button',name=name,exact=True)
            expect(btn).to_be_visible()
            box = btn.bounding_box()
            self.assertGreaterEqual(box['x'], 0)
            self.assertLessEqual(box['x'] + box['width'], 321)

    def test_18_not_injected_on_homepage(self):
        self.load(ACTIONS, path='/')
        self.page.wait_for_timeout(250)
        expect(self.actionbar()).to_have_count(0)

    def test_19_switch_tabs_mid_read_cancels(self):
        # With immediate extraction the old fixture has already finished copying.
        # Hold a real loading state to test a tab change DURING an active read.
        self.load(ACTIONS + panel(rows=ROWS + '<div aria-busy="true">Cargando transcripción</div>'))
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        expect(self.actionbar().get_by_role('button', name='Cancelar')).to_be_visible()
        self.page.evaluate('document.querySelector("#transcript-tab").setAttribute("aria-selected","false");document.querySelector("#chapters").setAttribute("aria-selected","true")')
        expect(self.actionbar().locator('.ytcopy-status')).to_contain_text('cambiado')
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_20_no_transcript_reports_error_not_success(self):
        self.load(ACTIONS)
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        expect(self.actionbar().locator('.ytcopy-status')).to_contain_text('No se ha encontrado', timeout=16000)
        self.assertEqual(self.page.evaluate('window.copied'), [])

    def test_21_preserves_native_click_handlers(self):
        self.load(ACTIONS + panel(), '() => {window.shareCount=0; document.querySelector("#share").onclick=()=>{window.shareCount++};}')
        self.assertEqual(self.page.evaluate('window.shareCount'), 0)
        self.page.locator('#share').click()
        self.assertEqual(self.page.evaluate('window.shareCount'), 1)
        self.assertEqual(self.page.locator('#menu button').all_text_contents(), ['Compartir','Descargar','Gracias','Más acciones'])

    def test_22_selects_matching_combined_model(self):
        self.load(ACTIONS + panel(target='PAmodern_transcript_view', tabs=False, hidden=True, ident='stale') + panel(), '''() => {
            const cue=(time,text)=>({transcriptSegmentRenderer:{startMs:String(time),snippet:{simpleText:text}}});
            document.querySelector('#stale').data={segments:[cue(40000,'No copiar texto viejo.')]};
            document.querySelector('#test-panel').data={segments:[cue(0,'Inicio de prueba.'),cue(5000,'Fin de prueba.'),cue(10000,'Final del modelo correcto.')]};
        }''')
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba. Final del modelo correcto.')

    def test_23_hidden_caption_rows_ignored(self):
        self.load(ACTIONS + panel(rows=ROWS + '<div hidden>'+ROWS.replace('prueba','NO VISIBLE')+'</div>'))
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.copied('Inicio de prueba. Fin de prueba.')

    def test_24_sidebar_rebuild_does_not_cancel_actionbar_read(self):
        self.load(ACTIONS + panel())
        self.actionbar().get_by_role('button', name='Copiar transcripción', exact=True).click()
        self.sidebar().evaluate('(el)=>el.remove()')
        expect(self.sidebar()).to_be_visible()
        self.copied('Inicio de prueba. Fin de prueba.')

if __name__ == '__main__':
    unittest.main()
