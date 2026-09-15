"""Desktop calendar regression and visual check with synthetic, offline data.

Usage: python tests/browser_check.py [--chromium /path/chromium] --output /tmp/preview
No upstream polling, real database access, or external browser requests.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.models import Snapshot
from app.store import Store


def fixture():
    def event(key, date, kind='direct_reset', status='confirmed', text='重置已全部推送完成。'):
        time = date + 'T16:09:00+08:00'
        return {'id': key, 'type': kind, 'status': status, 'title': 'Codex 额度重置已完成' if kind == 'direct_reset' else '新的重置卡已发放',
                'scope': 'Plus', 'createdAt': time, 'updatedAt': time, 'confirmedAt': time if status == 'confirmed' else None,
                'confirmationBasis': 'source_post' if status == 'confirmed' else None,
                'schedule': {'precision': 'window', 'from': date+'T11:00:00+08:00', 'label': '北京时间预计 15:00 前'},
                'posts': [{'id': key+'p1', 'publishedAt': time, 'stage': '确认完成', 'text': text, 'url': 'https://x.com/thsottiaux/status/123'},
                          {'id': key+'p2', 'publishedAt': date+'T11:20:00+08:00', 'stage': '原预告', 'text': '一次重置将在今天落地。', 'url': 'https://x.com/thsottiaux/status/124'}],
                'url': 'https://aihot.news/codex-reset'}
    rows = [event('reset', '2026-09-12'), event('credit', '2026-09-10', 'reset_credit'),
            event('older', '2026-09-08'), event('credit2', '2026-09-04', 'reset_credit'),
            event('preview', '2026-09-06', status='announced'), event('august', '2026-08-31'),
            event('leap', '2024-02-29')]
    rows += [event(f'many{i}', '2026-09-03', text='<img src=x onerror=alert(1)> '+('中文长帖内容。'*70)) for i in range(125)]
    now = datetime.now(timezone.utc).isoformat()
    return Snapshot.model_validate({'schemaVersion': 1, 'timezone': 'Asia/Shanghai', 'checkedAt': now,
                                    'historyFrom': '2024-01-01T00:00:00+08:00', 'count': len(rows), 'events': rows}), now


parser = argparse.ArgumentParser()
parser.add_argument('--chromium')
parser.add_argument('--output', required=True)
args = parser.parse_args()
out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
result = {}
with TemporaryDirectory() as directory:
    db = Path(directory) / 'test.db'
    snapshot, now = fixture()
    Store(db).sync(snapshot, {'last_success_at': now, 'checked_at': now, 'last_snapshot_at': now}, now)
    with TestClient(create_app(db, start_worker=False)) as client, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True,
                                   args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
        for name, width, height in [('desktop1440', 1440, 1050), ('desktop1280', 1280, 900)]:
            page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            held = []
            mode = {'value': 'normal'}
            def fulfill(route):
                u = urlsplit(route.request.url)
                if u.hostname != 'monitor.test':
                    route.abort(); raise AssertionError('unexpected external browser request')
                if u.path == '/api/calendar':
                    if mode['value'] == 'offline':
                        route.fulfill(status=503, body='offline'); return
                    if mode['value'] == 'bad-json':
                        route.fulfill(status=200, content_type='application/json', body='{}'); return
                    if mode['value'] == 'bad-shape':
                        data = client.get(u.path + '?' + u.query).json()
                        data['items'][0]['posts'] = None
                        route.fulfill(status=200, content_type='application/json', body=json.dumps(data)); return
                    if mode['value'] == 'delay-august' and parse_qs(u.query).get('month') == ['2026-08']:
                        held.append(route); return
                response = client.get(u.path + ('?' + u.query if u.query else ''))
                route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
            page.route('**/*', fulfill)
            page.goto('http://monitor.test/')
            page.locator('#refresh:enabled').wait_for()
            assert page.locator('.day').count() == 42
            assert page.locator('.day[aria-pressed="true"]').get_attribute('data-date') == '2026-09-12'
            assert page.locator('#day-events .post-card').count() == 2
            assert page.locator('.brand img').evaluate('(e)=>e.naturalWidth>0')
            assert page.locator('.brand').get_attribute('href') == 'https://leohub.cc'
            for theme in ['dark', 'light']:
                if page.locator('html').get_attribute('data-theme') != theme: page.locator('#theme').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / f'{name}-{theme}.png'), full_page=True)
            page.reload(); page.locator('#refresh:enabled').wait_for()
            assert page.locator('html').get_attribute('data-theme') == 'light'
            page.locator('[data-date="2026-09-10"]').click(); page.locator('#refresh:enabled').wait_for()
            assert '重置卡已发放' in page.locator('#day-events').inner_text()
            page.locator('[data-date="2026-09-15"]').click(); page.locator('#refresh:enabled').wait_for()
            assert '当天暂无记录' in page.locator('#day-events').inner_text()
            page.locator('[data-date="2026-09-03"]').click(); page.locator('#refresh:enabled').wait_for()
            assert page.locator('.day-event').count() == 20
            assert page.locator('#day-events img').count() == 0
            assert '125' in page.locator('#day-count').inner_text()
            assert page.locator('#day-scroll').evaluate('(e)=>e.scrollHeight>e.clientHeight')
            page.locator('#more').click(); page.locator('#refresh:enabled').wait_for()
            assert page.locator('.day-event').count() == 40
            page.locator('#latest').click(); page.locator('#refresh:enabled').wait_for()
            assert page.locator('.day[aria-pressed="true"]').get_attribute('data-date') == '2026-09-12'
            page.locator('[data-date="2026-08-31"]').click(); page.locator('#refresh:enabled').wait_for()
            assert '2026 年 08 月' == page.locator('#month-title').inner_text()
            page.locator('#next-month').click(); page.locator('#refresh:enabled').wait_for()
            # A late earlier request must not revert a newer month selection.
            mode['value'] = 'delay-august'
            page.locator('#previous-month').click()
            page.wait_for_timeout(60)
            assert held
            page.locator('#next-month').click(); page.locator('#refresh:enabled').wait_for()
            route = held.pop(); u = urlsplit(route.request.url)
            response = client.get(u.path + '?' + u.query)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
            page.wait_for_timeout(60)
            assert '2026 年 09 月' == page.locator('#month-title').inner_text()
            # Failed/invalid responses retain both the selected day and details.
            before = page.locator('#day-events').inner_text()
            for failure in ['offline', 'bad-json', 'bad-shape']:
                mode['value'] = failure
                page.locator('#refresh').click(); page.locator('#refresh:enabled').wait_for()
                assert page.locator('#client-error').is_visible()
                assert page.locator('#day-events').inner_text() == before
            mode['value'] = 'normal'
            page.locator('#refresh').click(); page.locator('#refresh:enabled').wait_for()
            assert page.locator('#client-error').is_hidden()
            assert not errors, errors
            result[name] = {'themes': True, 'calendar_and_details': True, 'day_pagination': True,
                            'late_response_guard': True, 'failure_preserves_view': True,
                            'literal_post_text': True, 'no_horizontal_overflow': True, 'js_errors': errors}
            page.close()
        browser.close()
(out / 'browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
