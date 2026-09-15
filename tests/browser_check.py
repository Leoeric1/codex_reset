"""Opt-in visual check against a local cache; never polls upstream or sends data externally.

Usage: python tests/browser_check.py --db /path/cache.db [--chromium /path/chromium] --output /tmp/preview
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from app.main import create_app

parser=argparse.ArgumentParser()
parser.add_argument('--db',required=True)
parser.add_argument('--chromium')
parser.add_argument('--output',required=True)
args=parser.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
result={}
with TestClient(create_app(args.db,start_worker=False)) as client, sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.chromium,headless=True,
                             args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
    for name,width,height in [('desktop',1440,1200),('mobile375',375,812),('mobile390',390,844),('mobile430',430,932)]:
        page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def fulfill(route):
            from urllib.parse import urlsplit
            u=urlsplit(route.request.url)
            response=client.get(u.path+('?' + u.query if u.query else ''))
            route.fulfill(status=response.status_code,headers=dict(response.headers),body=response.content)
        page.route('http://monitor.test/**',fulfill)
        page.goto('http://monitor.test/')
        page.locator('#refresh:enabled').wait_for()
        assert page.locator('.event').count()==10
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.locator('.brand').get_attribute('href')=='https://leohub.cc'
        assert page.locator('.brand img').evaluate('(e)=>e.naturalWidth>0')
        page.screenshot(path=str(out/(name+'-dark.png')),full_page=False)
        page.locator('#theme').click()
        assert page.locator('html').get_attribute('data-theme')=='light'
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(out/(name+'-light.png')),full_page=False)
        page.locator('#theme').click()
        page.locator('[data-filter="reset_credit"]').click()
        page.locator('#refresh:enabled').wait_for()
        assert page.locator('.event').count()>0
        assert all('重置卡' in t for t in page.locator('.event .badge').all_text_contents())
        page.locator('[data-filter="all"]').click();page.locator('#refresh:enabled').wait_for()
        page.locator('#more').click();page.locator('#more:enabled').wait_for(state='attached')
        page.wait_for_function('document.querySelectorAll(".event").length > 10')
        assert not errors, errors
        # Simulate failed local requests; the last rendered events must remain visible.
        count=page.locator('.event').count()
        page.route('http://monitor.test/api/**',lambda route:route.fulfill(status=503,body='offline'))
        page.locator('#refresh').click();page.locator('#client-error').wait_for(state='visible')
        assert page.locator('.event').count()==count
        result[name]={'width':width,'no_horizontal_overflow':True,'filter_and_pagination':True,
                      'failure_preserves_view':True,'js_errors':errors}
        page.close()
    browser.close()
(out/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
