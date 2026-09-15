from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.calendar import calendar_view
from app.main import create_app
from app.models import Snapshot
from app.store import Store
from test_monitor import event, snapshot, NOW


def save(store, rows):
    store.sync(Snapshot.model_validate(snapshot(rows)), {}, NOW.isoformat())


def at(key, timestamp, kind='direct_reset', status='confirmed'):
    row = event(key, status, kind)
    row.update(createdAt=timestamp, updatedAt=timestamp,
               confirmedAt=timestamp if status == 'confirmed' else None)
    row['posts'][0]['publishedAt'] = timestamp
    return row


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'calendar.db')


def test_full_month_counts_and_selected_day_pagination(store):
    save(store, [at(str(i), '2026-09-12T16:09:00+08:00') for i in range(125)])
    first = calendar_view(store, '2026-09', '2026-09-12', now=NOW)
    assert first['totals']['direct_reset'] == first['total'] == 125
    assert len(first['items']) == 20
    assert next(d for d in first['days'] if d['date'] == '2026-09-12')['total'] == 125
    ids = []
    for offset in range(0, 125, 20):
        ids += [e['id'] for e in calendar_view(store, '2026-09', '2026-09-12', offset, now=NOW)['items']]
    assert len(ids) == len(set(ids)) == 125


def test_utc_midnight_uses_beijing_confirmation_day(store):
    save(store, [at('boundary', '2026-08-31T16:01:00Z')])
    data = calendar_view(store, now=NOW)
    assert data['month'] == '2026-09'
    assert data['selected_date'] == '2026-09-01'
    assert data['items'][0]['time_precision'] == 'confirmed'


def test_date_only_is_not_replaced_by_post_date(store):
    row = at('date', '2026-09-12T16:09:00+08:00')
    row.update(confirmedAt=None, occurredOn='2026-09-10')
    save(store, [row])
    data = calendar_view(store, now=NOW)
    assert data['selected_date'] == '2026-09-10'
    assert data['items'][0]['time'] == '2026-09-10'
    assert data['items'][0]['time_precision'] == 'date'


def test_prediction_remains_posted_day_and_distinct_from_confirmation(store):
    row = at('announcement', '2026-09-12T16:09:00+08:00', status='announced')
    row['schedule'] = {'precision': 'window', 'from': '2026-10-01T00:00:00+08:00', 'label': '十月预告'}
    save(store, [row, at('credit', '2026-09-12T17:09:00+08:00', 'reset_credit')])
    data = calendar_view(store, now=NOW)
    assert data['selected_date'] == '2026-09-12'
    assert data['totals'] == {'direct_reset': 0, 'reset_credit': 1, 'announced': 1, 'total': 2}
    assert calendar_view(store, '2026-10', now=NOW)['totals']['total'] == 0


def test_event_posts_grouped_without_exposing_original_text(store):
    row = at('combined', '2026-09-12T16:09:00+08:00')
    row['posts'].append(dict(row['posts'][0], id='p2', stage='原预告', publishedAt='2026-09-11T08:00:00+08:00'))
    save(store, [row])
    data = calendar_view(store, now=NOW)
    assert data['total'] == 1
    assert len(data['items'][0]['posts']) == 2
    assert all('originalText' not in p for p in data['items'][0]['posts'])
    assert all(set(d) == {'date', 'direct_reset', 'reset_credit', 'announced', 'total'} for d in data['days'])


def test_leap_month_and_neighbor_month_cells(store):
    save(store, [at('leap', '2024-02-29T12:00:00+08:00'), at('neighbor', '2024-03-01T12:00:00+08:00')])
    data = calendar_view(store, '2024-02', now=NOW)
    assert len(data['days']) == 42
    assert data['days'][0]['date'] == '2024-01-29'
    assert data['days'][-1]['date'] == '2024-03-10'
    assert data['totals']['total'] == 1
    assert data['selected_date'] == '2024-02-29'
    assert next(d for d in data['days'] if d['date'] == '2024-03-01')['total'] == 1


def test_empty_calendar_uses_beijing_today_and_requested_empty_day(store):
    data = calendar_view(store, now=datetime(2025, 12, 31, 18, tzinfo=timezone.utc))
    assert data['month'] == '2026-01'
    assert data['today'] == data['selected_date'] == '2026-01-01'
    assert data['items'] == [] and data['latest_date'] is None
    assert calendar_view(store, now=NOW)['selected_date'] == '2026-09-14'
    assert calendar_view(store, day='2026-02-15', now=NOW)['selected_date'] == '2026-02-15'


def test_calendar_reads_do_not_mutate_notifications_or_poll(store, monkeypatch):
    from app.monitor import Monitor
    async def forbidden(*args):
        raise AssertionError('calendar must not poll AIHOT')
    monkeypatch.setattr(Monitor, 'poll', forbidden)
    save(store, [at('one', '2026-09-12T16:09:00+08:00')])
    before = store.notification_feed(NOW)
    with TestClient(create_app(store.path, start_worker=False)) as client:
        response = client.get('/api/calendar?month=2026-09&limit=100')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/api/events').json()['limit'] == 30
    assert store.notification_feed(NOW) == before


def test_withdrawal_disappears_from_calendar(store):
    save(store, [at('removed', '2026-09-12T16:09:00+08:00')])
    save(store, [])
    data = calendar_view(store, '2026-09', '2026-09-12', now=NOW)
    assert data['total'] == data['totals']['total'] == 0
    assert data['items'] == []


@pytest.mark.parametrize('query', [
    'month=2026-13', 'month=2026-00', 'month=2026-1', 'month=0001-01',
    'day=2026-02-30', 'day=2026-9-1', 'month=2026-09&day=2026-10-01',
    'limit=101', 'limit=0', 'offset=-1',
])
def test_invalid_calendar_queries_are_rejected(store, query):
    with TestClient(create_app(store.path, start_worker=False)) as client:
        assert client.get('/api/calendar?' + query).status_code == 422
