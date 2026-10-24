"""Priority Watch persistence and workflow API tests. These labels are not collision probabilities."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from ofde.service import OfdeService, ROUTES

ROUTE = {r.handler: r for r in ROUTES}


def call(svc, handler, params=None, query=None, body=None):
    raw = json.dumps(body).encode() if body is not None else None
    status, ctype, data, headers = svc.handle(ROUTE[handler], params or {}, query or {}, raw)
    return status, json.loads(data) if ctype.startswith("application/json") else data.decode()


class TestPriorityWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "watch.sqlite3")
        self.svc = OfdeService(self.db, clock=lambda: datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc))

    def tearDown(self):
        self.svc.store.close()
        self.tmp.cleanup()

    def test_create_list_acknowledge_and_review_persist(self):
        status, result = call(self.svc, "create_priority_watch", body={
            "priority": "critical", "reason": "Operator review requested: inspect saved result and source quality.",
            "restricted_label": "restricted"})
        self.assertEqual(status, 200, result)
        alert = result["alert"]
        self.assertEqual(alert["priority"], "critical")
        self.assertEqual(alert["restricted_label"], "restricted")
        self.assertEqual(alert["status"], "open")
        self.assertIn("2026-10-24", alert["created_utc"])

        status, result = call(self.svc, "acknowledge_priority_watch", {"alert_id": str(alert["id"])}, body={})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["alert"]["status"], "acknowledged")

        status, result = call(self.svc, "review_priority_watch", {"alert_id": str(alert["id"])}, body={})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["alert"]["status"], "reviewed_resolved")
        self.svc.store.close()
        self.svc = OfdeService(self.db)
        status, result = call(self.svc, "list_priority_watch")
        self.assertEqual(status, 200)
        self.assertEqual(result["alerts"][0]["status"], "reviewed_resolved")
        self.assertIn("not collision probabilities", result["notice"])

    def test_requires_reason_and_rejects_unknown_labels(self):
        status, result = call(self.svc, "create_priority_watch", body={"priority": "critical", "reason": "  "})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "INVALID_INPUT")
        status, result = call(self.svc, "create_priority_watch", body={"priority": "critical", "reason": "Review", "restricted_label": "urgent"})
        self.assertEqual(status, 400)

    def test_missing_alert_returns_not_found(self):
        status, result = call(self.svc, "review_priority_watch", {"alert_id": "999"}, body={})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
