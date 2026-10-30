"""Visit the deployed app, wake it if needed, and verify a real data tab.

Read-only browser traffic: never collect data, write the snapshot, or push Git.
"""
import json
import os
import re
from pathlib import Path
import shutil
import time

from playwright.sync_api import expect, sync_playwright


URL = "https://oil-field-map-demo-mpsslyxypuc6vwdxnmap3o.streamlit.app/"


def main():
    output = Path("runtime/keepalive")
    output.mkdir(parents=True, exist_ok=True)
    result = {"url": URL, "status": "unavailable", "wake_requested": False}
    with sync_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox"]}
        executable = shutil.which("google-chrome") or shutil.which("chromium")
        if executable:
            options["executable_path"] = executable
        if os.environ.get("HTTPS_PROXY"):
            options["proxy"] = {"server": os.environ["HTTPS_PROXY"]}
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                # Community Cloud may wrap both the sleeping page and the app
                # in a cross-origin iframe; the top-level shell has no text.
                for frame in page.frames:
                    error = frame.locator('[data-testid="stException"]')
                    if error.count():
                        result.update(status="app_error", error=error.all_inner_texts())
                        break
                    tab = frame.get_by_role("tab", name="油气", exact=True)
                    if tab.count() and tab.is_visible():
                        tab.click()
                        frame.locator('[data-testid="stDataFrame"]').first.wait_for(
                            state="visible", timeout=30_000)
                        if error.count():
                            result.update(status="app_error", error=error.all_inner_texts())
                        else:
                            result.update(status="ready", tabs=frame.get_by_role("tab").all_text_contents(),
                                          metrics=frame.locator('[data-testid="stMetric"]').all_inner_texts())
                            crude = frame.locator('.st-key-production_daily_metric')
                            expect(crude).to_contain_text('原油产量', timeout=30_000)
                            crude_value = crude.locator('[data-testid="stMetricValue"]').inner_text()
                            if not re.fullmatch(r'\d+\.\d万桶/日', crude_value):
                                raise RuntimeError(f'Unexpected crude oil total format: {crude_value}')
                            result['crude_oil_total'] = crude_value
                            frame.get_by_role("tab", name="地图", exact=True).click()
                            cards = frame.locator('.monitoring-card')
                            expect(cards).to_have_count(3, timeout=30_000)
                            labels = cards.locator(':scope > span').all_text_contents()
                            if labels != ["港口监测", "咽喉点监测", "油田监测"]:
                                raise RuntimeError(f"Unexpected map monitoring cards: {labels}")
                            result["map_cards"] = labels
                            result["map_card_details"] = cards.all_inner_texts()
                            if cards.locator('.monitoring-card-detail').count():
                                raise RuntimeError('Monitoring cards still contain text below their main values')
                            if any(text in ''.join(result['map_card_details']) for text in
                                   ['已披露进港', '已披露通过', '独立统计', '日记录覆盖', '非同日', '产量数据：']):
                                raise RuntimeError('Monitoring card explanation text is still present')
                            frame.get_by_role('tab', name='港口', exact=True).click()
                            port_metrics = frame.locator('[data-testid="stMetric"]')
                            expect(port_metrics).to_have_count(8, timeout=30_000)
                            result['port_metrics'] = port_metrics.all_inner_texts()
                            if any(value == '—' or value.startswith('—（') for value in
                                   port_metrics.locator('[data-testid="stMetricValue"]').all_inner_texts()[1:]):
                                raise RuntimeError('Available port activity metrics are still blank')
                            frame.get_by_role('tab', name='船舶', exact=True).click()
                            frame.locator('[data-testid="stImage"]').first.wait_for(
                                state='visible', timeout=45_000)
                            if error.count():
                                raise RuntimeError(str(error.all_inner_texts()))
                            result['vessel_chart_count'] = frame.locator('[data-testid="stImage"]').count()
                        break
                    wake = frame.get_by_role("button", name="Yes, get this app back up!", exact=True)
                    if not result["wake_requested"] and wake.count() and wake.is_visible():
                        wake.click()
                        result["wake_requested"] = True
                        print("Wake requested; waiting for the data tab.", flush=True)
                if result["status"] != "unavailable":
                    break
                page.wait_for_timeout(3000)
            result["page_text"] = page.locator("body").inner_text()[:4000]
            result["frames"] = []
            for frame in page.frames:
                try:
                    from urllib.parse import urlsplit
                    parsed = urlsplit(frame.url)
                    result["frames"].append({"url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
                                             "text": frame.locator("body").inner_text(timeout=2000)[:4000]})
                except Exception:
                    continue  # A frame can detach while the app wakes.
        except Exception as exc:
            result.update(status="unavailable", error=str(exc)[:2000])
        finally:
            page.screenshot(path=str(output / "page.png"), full_page=True)
            browser.close()
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write(f"App browser check: **{result['status']}**; "
                         f"wake requested: {result['wake_requested']}. "
                         "See the screenshot and result artifact.\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
