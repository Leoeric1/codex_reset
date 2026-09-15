import asyncio
import json
import sqlite3
from datetime import timedelta
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.store import Store
from app.notifications import create_sender
from test_monitor import NOW, event, snapshot, poll, seed

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'feed.db')

def sync(store, events, minute=5):
    now=NOW+timedelta(minutes=minute)
    poll(store,httpx.Response(200,json=snapshot(events,now)),now)
    return store.notification_feed(now,after=0,limit=100)

def test_initial_history_and_restart_are_suppressed(store):
    seed(store,[event('old','confirmed')])
    assert store.notification_feed(NOW)['items']==[]
    assert Store(store.path).notification_feed(NOW,after=0)['cursor']==0

@pytest.mark.parametrize('kind,status', [('direct_reset','confirmed'),('reset_credit','confirmed'),('direct_reset','announced'),('reset_credit','announced')])
def test_new_event_types(store,kind,status):
    seed(store,[])
    feed=sync(store,[event('new',status,kind)])
    assert len(feed['items'])==1
    item=feed['items'][0]['item']
    assert (item['type'],item['status'])==(kind,status)
    assert item['time_label'] and item['time_precision']


def test_transition_cancels_announcement_and_adds_confirmation(store):
    seed(store,[])
    sync(store,[event('new')])
    feed=sync(store,[event('new','confirmed')],10)
    assert feed['cursor']==3
    assert feed['items'][0]['operation']=='cancel' # Projection never resurrects old state.
    assert feed['items'][-1]['item']['kind']=='reset_confirmed'


def test_text_revision_preserves_notification_identity_and_creation(store):
    seed(store,[]); e=event('new','confirmed')
    before=sync(store,[e])['items'][0]['item'];e['posts'][0]['text']='修订中文'
    after=sync(store,[e],10)['items'][-1]['item']
    assert before['notification_id']==after['notification_id']
    assert before['created_at']==after['created_at']
    assert len(store.notification_feed(NOW)['items'])==1
    with store.connection() as db: assert db.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==1


def test_restart_identical_snapshot_does_not_add_changes(store):
    seed(store,[]);sync(store,[event('new','confirmed')]);store=Store(store.path)
    assert sync(store,[event('new','confirmed')],10)['cursor']==1


def test_withdrawal_and_reappearance_do_not_realert(store):
    seed(store,[]); sync(store,[event('new','confirmed')]); feed=sync(store,[],10)
    assert feed['items'][-1]['operation']=='cancel'
    assert store.notification_feed(NOW)['items']==[]
    assert sync(store,[event('new','confirmed')],15)['cursor']==2


def test_failure_preserves_notifications_and_cursor(store):
    seed(store,[]);sync(store,[event('new','confirmed')]);before=store.notification_feed(NOW,after=0)
    poll(store,httpx.Response(503),NOW+timedelta(minutes=10))
    assert store.notification_feed(NOW,after=0)==before


def test_feed_pagination_has_no_loss_and_rejects_ahead_cursor(store):
    seed(store,[]);sync(store,[event(str(i),'confirmed') for i in range(35)])
    cursor=0; ids=[]
    while True:
        page=store.notification_feed(NOW,after=cursor,limit=10)
        ids.extend(i['notification_id'] for i in page['items']);cursor=page['next_cursor']
        if not page['has_more']:break
    assert len(ids)==len(set(ids))==35
    with pytest.raises(ValueError):store.notification_feed(NOW,after=36)


def test_api_limits_projection_and_initialization(tmp_path):
    with TestClient(create_app(tmp_path/'api.db',start_worker=False)) as c:
        assert c.get('/api/notifications/latest').json()['initialized'] is False
        seed(c.app.state.store,[]);sync(c.app.state.store,[event(str(i),'confirmed') for i in range(15)])
        r=c.get('/api/notifications/latest'); assert len(r.json()['items'])==10
        assert c.get('/api/notifications/latest?limit=11').status_code==422
        assert c.get('/api/notifications/changes?limit=101').status_code==422
        assert c.get('/api/notifications/changes?after=100').status_code==409
        assert not any(x in r.text for x in ['originalText','etag','raw_json','disposition','sent_at','snapshot'])


def test_disabled_sender_never_sends_network(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('network')
    monkeypatch.setenv('NOTIFICATION_PROVIDER','disabled');monkeypatch.setenv('PUSHPLUS_TOKEN','test-unused')
    monkeypatch.setattr(httpx.AsyncClient,'send',forbidden)
    assert asyncio.run(create_sender().send({'id':'test'}))=='disabled'
    monkeypatch.setenv('NOTIFICATION_PROVIDER','pushplus')
    assert asyncio.run(create_sender().send({'id':'test'}))=='disabled'


def test_upgrade_existing_disabled_rows_never_backfills(tmp_path):
    path=tmp_path/'old.db'
    # Exact V1 schema, populated before notification stream migration.
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE notifications(event_id TEXT, notification_type TEXT, disposition TEXT, created_at TEXT, sent_at TEXT, PRIMARY KEY(event_id,notification_type));')
        db.execute("INSERT INTO notifications VALUES ('legacy','reset_confirmed','disabled',?,NULL)",(NOW.isoformat(),))
    store=Store(path); seed(store,[event('legacy','confirmed')]); assert store.notification_feed(NOW)['items']==[]
    sync(store,[event('legacy','confirmed'),event('fresh','confirmed')])
    assert [i['event_id'] for i in store.notification_feed(NOW)['items']]==['fresh']


def test_date_only_precision_and_expiry(store):
    seed(store,[]); e=event('date','confirmed');e['confirmedAt']=None;e['occurredOn']='2026-09-14'
    sync(store,[e,event('announcement')]);items=store.notification_feed(NOW)['items']
    date=next(i for i in items if i['event_id']=='date')
    assert date['time']=='2026-09-14' and date['time_precision']=='date'
    assert len(store.notification_feed(NOW+timedelta(days=2))['items'])==1
