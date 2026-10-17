"""Manual regression: python tests/browser_3d_iframe.py (requires Playwright).

Real Cesium + real imagery/terrain inside compressed sandbox/srcdoc. CDN worker
requests are deliberately refused: the frame-owned worker bundle must suffice.
No business data or database is read or modified.
"""
import html
from pathlib import Path
import sys
import tempfile

import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from map_3d import build_3d_html


def run():
    document = build_3d_html(
        assets=[], ports=[{'popupKey':'port:test','name':'测试港（Test Port）',
                          'lon':55,'lat':25.05,'popup':'<b>港口详情</b>'}],
        chokepoints=[], vessels=[], pipelines={'features':[]}, tracks={},
        legend='图例', dates='港口数据日：2026-10-09',
        focus={'key':'port:test','revision':1}, screenshot=False,
        google_key='', ion_token='')
    host = '<iframe style="width:100%;height:735px" sandbox="allow-scripts allow-same-origin" srcdoc="' + html.escape(document,quote=True) + '"></iframe>'
    errors, worker_errors, external_workers = [], [], []
    cache = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width':1300,'height':800})
        context.add_init_script("""
            window.workerFailures=[];
            const OriginalWorker=Worker;
            window.Worker=class extends OriginalWorker {
              constructor(...args) {super(...args);this.addEventListener('error',()=>window.workerFailures.push(String(args[0])));}
            };
        """)
        page = context.new_page()
        page.on('pageerror',lambda error: errors.append(str(error)))

        def network(route):
            url = route.request.url
            if url.startswith('http://127.0.0.1:8765/'):
                route.fulfill(body=host,content_type='text/html'); return
            if '/Workers/' in url:
                external_workers.append(url); route.abort(); return
            if url not in cache:
                response = requests.get(url,timeout=20)
                response.raise_for_status()
                cache[url] = (response.content, {
                    key:value for key,value in response.headers.items()
                    if key.lower() in ('content-type','access-control-allow-origin')})
            body, headers = cache[url]
            route.fulfill(body=body,headers=headers)

        context.route('**/*',network)
        page.goto('http://127.0.0.1:8765/',wait_until='domcontentloaded')
        frame = page.frames[1]
        frame.wait_for_function('window.energy3d !== undefined',timeout=120000)
        frame.wait_for_function('energy3d.viewer.scene.globe.tilesLoaded',timeout=120000)
        assert frame.evaluate('Cesium.TaskProcessor._canTransferArrayBuffer') is True
        assert frame.evaluate('energy3d.viewer.scene.globe._surface._tilesToRender.length') > 0
        assert frame.evaluate('energy3d.viewer.selectedEntity.id') == 'port:test'
        assert frame.locator('#content').inner_text() == '港口详情'
        assert frame.locator('#detail').is_visible()
        worker_errors.extend(frame.evaluate('window.workerFailures'))
        assert not errors, errors
        assert not worker_errors, worker_errors
        assert not external_workers, external_workers
        with tempfile.TemporaryDirectory() as temporary:
            page.screenshot(path=str(Path(temporary)/'3d-iframe.png'))
        browser.close()
    print('PASS: compressed srcdoc, real terrain meshes, imagery, focus and popup; no external workers')


if __name__ == '__main__':
    run()
