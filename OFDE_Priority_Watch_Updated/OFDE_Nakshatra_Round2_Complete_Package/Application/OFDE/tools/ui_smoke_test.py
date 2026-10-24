"""Optional end-to-end browser check against a RUNNING real backend (needs: pip install playwright; playwright install chromium).

    python -m ofde            # in one terminal
    python tools/ui_smoke_test.py --url http://127.0.0.1:8000   # in another

Loads the synthetic demo pair into the workspace, runs an analysis with the real SGP4 backend, and checks that the
COMPUTED result, history row and the four exports exist. Exits non-zero on any failure. NOT run in the build sandbox.
"""
import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && playwright install chromium")
        return 2
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1360, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(a.url)
        pg.wait_for_selector("#demo")
        assert "Backend connected" in pg.inner_text("#chips"), "backend not connected"
        pg.click("#demo")
        pg.wait_for_selector("#va >> text=Valid TLE")
        pg.click("#example")
        pg.click("#run")
        pg.wait_for_selector("#resultsroot", timeout=60000)
        text = pg.inner_text("#resultsroot")
        assert "COMPUTED" in text, "result is not labelled COMPUTED"
        links = [x.get_attribute("href") for x in pg.query_selector_all("#resultsroot a.btn")]
        assert len(links) == 4, f"expected 4 export links, got {links}"
        for h in links:
            r = pg.request.get(a.url + h)
            assert r.status == 200, f"{h} -> {r.status}"
        pg.click(".topbar nav button[data-tab=history]")
        pg.wait_for_selector("text=Open and export")
        assert len(pg.query_selector_all("tbody tr")) >= 1, "history empty"
        b.close()
    if errors:
        print("JavaScript errors:", errors)
        return 1
    print("UI smoke test passed (real backend).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
