"""Visit the deployed app, wake it if needed, and verify a real data tab.

Read-only browser traffic: never collect data, write the snapshot, or push Git.
"""
import json
import os
from pathlib import Path
import shutil
import time

from playwright.sync_api import sync_playwright


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
                error = page.locator('[data-testid="stException"]')
                if error.count():
                    result.update(status="app_error", error=error.all_inner_texts())
                    break
                tab = page.get_by_role("tab", name="油气", exact=True)
                if tab.count() and tab.is_visible():
                    tab.click()
                    page.locator('[data-testid="stDataFrame"]').first.wait_for(
                        state="visible", timeout=30_000)
                    # Recheck after the data tab renders, not just the shell.
                    if error.count():
                        result.update(status="app_error", error=error.all_inner_texts())
                    else:
                        result.update(status="ready", tabs=page.get_by_role("tab").all_text_contents(),
                                      metrics=page.locator('[data-testid="stMetric"]').all_inner_texts())
                    break
                wake = page.get_by_role("button", name="Yes, get this app back up!", exact=True)
                if not result["wake_requested"] and wake.count() and wake.is_visible():
                    wake.click()
                    result["wake_requested"] = True
                    print("Wake requested; waiting for the data tab.", flush=True)
                page.wait_for_timeout(3000)
            result["page_text"] = page.locator("body").inner_text()[:4000]
        except Exception as exc:
            result["error"] = str(exc)[:2000]
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
