"""Private Hub projection and a deliberately inert external delivery boundary."""
import os
import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from .monitor import present, dt, iso


class NotificationSender(ABC):
    @abstractmethod
    async def send(self, notification):
        """Return a delivery outcome; never change event/snapshot transactions."""


class DisabledNotificationSender(NotificationSender):
    async def send(self, notification):
        return 'disabled'


def create_sender():
    # Unsupported providers fail closed; adding a token never enables delivery.
    if os.getenv('NOTIFICATION_PROVIDER', 'disabled') != 'disabled':
        logging.getLogger('codex-reset-monitor').warning('Unsupported notification provider; external delivery remains disabled')
    return DisabledNotificationSender()


def notification_id(event_id, kind):
    return event_id + ':' + kind


def project(raw, kind, created_at, now):
    e = present(raw, now)
    expiry = None
    if e['status'] == 'announced':
        s = e.get('schedule') or {}
        expiry = s.get('through') or s.get('from') or iso(dt(e['announced_at']) + timedelta(days=1))
    labels = {'confirmed': '确认帖发布', 'date': '核验日期', 'post': '原帖发布'}
    return {'notification_id': notification_id(e['id'], kind), 'event_id': e['id'],
            'kind': kind, 'type': e['type'], 'status': e['status'],
            'title': ('新的重置卡' if e['type'] == 'reset_credit' else '新的全员重置') + ('确认' if e['status'] == 'confirmed' else '预告'),
            'time': e['time'], 'time_precision': e['time_precision'],
            'time_label': labels[e['time_precision']], 'created_at': created_at,
            'expires_at': expiry, 'source_url': next((p['url'] for p in e['posts'] if p['url']), e['source_url'])}
