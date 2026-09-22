"""Delivery extension point. Polling only queues durable events by default."""
from typing import Protocol
import requests


class Sender(Protocol):
    def send(self, event: dict) -> None:
        """Raise on failure; use event['id'] as a deduplication key."""
        ...


class WebhookSender:
    """Opt-in JSON POST; an application supplies its endpoint at dispatch time."""
    def __init__(self, url: str, token: str = ""):
        if not url.startswith("https://"):
            raise ValueError("Webhook 必须使用 HTTPS")
        self.url, self.token = url, token

    def send(self, event):
        headers = {"Idempotency-Key": event["id"]}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        response = requests.post(self.url, json=event, headers=headers, timeout=(10, 30),
                                 allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"通知接口 HTTP {response.status_code}")


def dispatch(db, sender: Sender, limit=100):
    """At-least-once delivery; mark each event delivered only after success."""
    import json
    sent = 0
    for event_id, payload in db.execute(
        "SELECT id,payload FROM events WHERE delivered=0 ORDER BY rowid LIMIT ?", (limit,)
    ).fetchall():
        sender.send(json.loads(payload))
        with db:
            db.execute("UPDATE events SET delivered=1 WHERE id=?", (event_id,))
        sent += 1
    return sent
