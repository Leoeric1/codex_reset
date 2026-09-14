import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Snapshot
from app.monitor import Monitor, dt, iso, present, retry_delay, views
from app.store import Store

NOW = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)


def event(key="r1", status="announced", kind="direct_reset"):
    return {"id": key, "type": kind, "status": status, "title": "测试重置", "scope": "Plus",
            "createdAt": iso(NOW), "updatedAt": iso(NOW), "confirmedAt": iso(NOW) if status == "confirmed" else None,
            "occurredOn": None, "confirmationBasis": "source_post" if status == "confirmed" else None,
            "schedule": {"precision": "window", "from": iso(NOW+timedelta(hours=1)),
                         "through": iso(NOW+timedelta(hours=2)), "label": "预计 09:00–10:00"},
            "posts": [{"id": "p1", "publishedAt": iso(NOW), "stage": "预告", "text": "测试中文",
                       "originalText": "test", "url": "https://x.com/thsottiaux/status/123"}],
            "url": "https://aihot.news/codex-reset"}


def snapshot(events=None, checked=NOW):
    rows=[event()] if events is None else events
    return {"schemaVersion":1,"timezone":"Asia/Shanghai","checkedAt":iso(checked) if checked else None,
            "historyFrom":"2026-06-12T00:00:00+08:00","count":len(rows),"events":rows}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def poll(store, response, now=NOW, requests=None):
    def handler(request):
        if requests is not None: requests.append(request)
        return response
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await Monitor(store,c,lambda:now).poll()
    return asyncio.run(run())


def seed(store, rows=None):
    poll(store, httpx.Response(200,json=snapshot(rows),headers={"ETag":'W/"first"'}))


def test_snapshot_modify_remove_and_etag_atomically(store):
    seed(store,[event("a"),event("b")]);now=NOW+timedelta(minutes=5)
    poll(store,httpx.Response(200,json=snapshot([event("a","confirmed")],now),headers={"ETag":'"second"'}),now)
    s,rows=store.read()
    assert [e["id"] for e in rows]==["a"] and rows[0]["status"]=="confirmed"
    assert s["last_diff"]=={"added":0,"removed":1,"modified":1} and s["etag"]=='"second"'
    with store.connection() as db:
        assert db.execute("SELECT disposition FROM notifications WHERE event_id='b'").fetchone()[0]=='cancelled'


def test_304_connection_success_without_forging_checked_at(store):
    seed(store);before=store.read()[0];req=[];now=NOW+timedelta(minutes=5)
    poll(store,httpx.Response(304),now,req)
    after,rows=store.read()
    assert req[0].headers["if-none-match"]=='W/"first"'
    assert after["checked_at"]==before["checked_at"] and after["last_success_at"]==iso(now)
    assert after["last_snapshot_at"]==before["last_snapshot_at"] and len(rows)==1


def test_304_stale_upstream_is_degraded_even_if_connection_works(store):
    seed(store);now=NOW+timedelta(minutes=31);poll(store,httpx.Response(304),now)
    s,_=views(store,now)
    assert s["source"]=='stale' and s["status"]=='degraded' and s["connection_age_seconds"]==0


@pytest.mark.parametrize('mutation',[lambda d:d.update(count=2),lambda d:d.pop('events'),
    lambda d:d.update(events=[event(),event()],count=2),lambda d:d.update(schemaVersion=2),
    lambda d:d['events'][0].update(type='new_type'),lambda d:d['events'][0].update(createdAt='2026-09-14T01:00:00')])
def test_bad_snapshot_preserves_events_and_etag(store,mutation):
    seed(store);d=snapshot();mutation(d)
    poll(store,httpx.Response(200,json=d,headers={'ETag':'"bad"'}),NOW+timedelta(minutes=5))
    s,rows=store.read();assert s['etag']=='W/"first"' and len(rows)==1 and s['consecutive_failures']==1


def test_empty_snapshot_clears_events(store):
    seed(store);poll(store,httpx.Response(200,json=snapshot([])),NOW+timedelta(minutes=5))
    assert store.read()[1]==[]


@pytest.mark.parametrize('code',[429,503])
def test_retry_after_survives_restart(store,code):
    seed(store);now=NOW+timedelta(minutes=5)
    delay=poll(store,httpx.Response(code,headers={'Retry-After':'7200'}),now)
    assert delay==7200
    requests=[]
    remaining=poll(Store(store.path),httpx.Response(200,json=snapshot()),now+timedelta(minutes=10),requests)
    assert requests==[] and remaining==6600


def test_retry_after_http_date_and_fallback():
    assert retry_delay('Mon, 14 Sep 2026 02:00:00 GMT',NOW)==7200
    assert retry_delay('1',NOW)==300
    assert retry_delay('bad',NOW) is None
    assert retry_delay('inf',NOW) is None


def test_backoff_recovery_and_failure_thresholds(store):
    seed(store);now=NOW+timedelta(minutes=5)
    for n in range(1,7):
        delay=poll(store,httpx.Response(503),now)
        s,_=views(store,now)
        if n==1:assert s['color']=='green'
        if n==3:assert s['color']=='yellow'
        if n==6:assert s['color']=='red'
        now+=timedelta(seconds=delay)
    poll(store,httpx.Response(200,json=snapshot(checked=now)),now)
    s,_=views(store,now);assert s['consecutive_failures']==0 and s['color']=='green'


def test_notifications_initial_suppressed_transition_dedup_and_no_sender(store):
    seed(store);now=NOW+timedelta(minutes=5)
    poll(store,httpx.Response(200,json=snapshot([event(status='confirmed')],now)),now)
    now+=timedelta(minutes=5)
    poll(store,httpx.Response(200,json=snapshot([event(status='confirmed')],now)),now)
    with store.connection() as db:
        rows=list(db.execute('SELECT disposition,sent_at FROM notifications'))
    assert len(rows)==2 and all(r['sent_at'] is None for r in rows)
    assert any(r['disposition']=='disabled' for r in rows)


def test_expired_and_unknown_announcements_are_not_upcoming(store):
    seed(store)
    s,rows=views(store,NOW+timedelta(days=2))
    assert not s['announcements'] and rows[0]['status']=='announced' and rows[0]['expired']
    e=event();e['schedule']=None
    assert present(e,NOW+timedelta(days=2))['expired']


def test_receipt_dates_unknown_times_and_safe_urls(store):
    e=event(kind='reset_credit',status='confirmed');e['confirmedAt']=None;e['occurredOn']='2026-09-13';e['confirmationBasis']='receipt_review'
    e['posts'][0]['url']='javascript:alert(1)'
    p=present(e,NOW)
    assert p['time']=='2026-09-13' and p['time_precision']=='date' and p['posts'][0]['url'] is None
    e['occurredOn']=None;assert present(e,NOW)['time_precision']=='post'
    assert 'originalText' not in json.dumps(p)


def test_null_checked_at_is_valid_and_degraded(store):
    poll(store,httpx.Response(200,json=snapshot(checked=None)))
    s,_=views(store,NOW);assert s['has_data'] and s['status']=='degraded' and s['checked_at'] is None


def test_future_and_regressed_snapshot_rejected(store):
    seed(store)
    for n,checked in enumerate([NOW+timedelta(days=1),NOW-timedelta(days=1)]):
        poll(store,httpx.Response(200,json=snapshot([],checked)),NOW+timedelta(minutes=5*(n+1)))
        assert len(store.read()[1])==1


def test_write_failure_never_advances_etag(store,monkeypatch):
    seed(store)
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(store,'sync',fail)
    poll(store,httpx.Response(200,json=snapshot([]),headers={'etag':'"new"'}),NOW+timedelta(minutes=5))
    s,rows=store.read();assert s['etag']=='W/"first"' and len(rows)==1


def test_routes_health_and_private_projection(tmp_path):
    path=tmp_path/'web.db'
    with TestClient(create_app(path,start_worker=False)) as c:
        assert c.get('/health').status_code==503 and c.get('/live').status_code==200
        response=c.get('/');assert response.status_code==200 and "frame-ancestors 'none'" in response.headers['content-security-policy']
        seed(c.app.state.store,[event('a','confirmed'),event('b',kind='reset_credit')])
        rows=c.get('/api/events?type=reset_credit&limit=1').json()
        assert rows['total']==1 and rows['items'][0]['type']=='reset_credit'
        assert c.get('/api/events?limit=101').status_code==422
        assert c.get('/api/events?type=invalid').status_code==422
        assert c.get('/api/events/latest').status_code==200
        body=c.get('/api/status').json();assert 'etag' not in body
        assert 'raw_json' not in c.get('/api/events').text
        assert c.get('/openapi.json').status_code==404


def test_success_health_returns_200(tmp_path):
    from app.monitor import utcnow
    now=utcnow()
    with TestClient(create_app(tmp_path/'web.db',start_worker=False)) as c:
        poll(c.app.state.store,httpx.Response(200,json=snapshot(checked=now)),now)
        assert c.get('/health').status_code==200


def test_network_timeout_keeps_cache(store):
    seed(store)
    def fail(request): raise httpx.ReadTimeout('offline',request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as c:
            await Monitor(store,c,lambda:NOW+timedelta(minutes=5)).poll()
    asyncio.run(run())
    s,rows=store.read()
    assert len(rows)==1 and s['last_error']=='ReadTimeout' and s['etag']=='W/"first"'


def test_oversized_snapshot_does_not_replace_cache(store):
    seed(store)
    poll(store,httpx.Response(200,content=b' '*(4*1024*1024+1)),NOW+timedelta(minutes=5))
    s,rows=store.read();assert len(rows)==1 and s['consecutive_failures']==1


def test_single_worker_lock_rejects_duplicate(tmp_path):
    import fcntl
    path=tmp_path/'locked.db'
    with open(str(path)+'.worker.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            with TestClient(create_app(path,start_worker=True)):
                pass
