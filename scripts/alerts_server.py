#!/usr/bin/env python3
"""
簡易アラート閲覧サーバ

起動:
    python3 scripts/alerts_server.py --db db/monitor.db --host 0.0.0.0 --port 8000

エンドポイント:
    GET /health
    GET /alerts?since_id=<int>&limit=<int>
    GET /view  (簡易HTML、5秒間隔でポーリング)
"""
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


def fetch_alerts(db_path: str, since_id: int = 0, limit: int = 50):
    limit = max(1, min(limit, 200))  # 1-200に制限
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.id,
            a.alert_type,
            a.status,
            a.created_at,
            le.id AS log_id,
            le.classification,
            le.severity,
            IFNULL(le.anomaly_reason, '') AS anomaly_reason,
            le.message
        FROM alerts a
        JOIN log_entries le ON le.id = a.log_id
        WHERE a.id > ?
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (since_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


class AlertHandler(BaseHTTPRequestHandler):
    def _set_json(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def _set_html(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._set_json()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return

        if parsed.path == "/alerts":
            qs = parse_qs(parsed.query)
            since_id = int(qs.get("since_id", ["0"])[0] or 0)
            limit = int(qs.get("limit", ["50"])[0] or 50)
            alerts = fetch_alerts(self.server.db_path, since_id, limit)
            self._set_json()
            self.wfile.write(json.dumps(alerts, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/view":
            self._set_html()
            html = """
<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Alerts Viewer</title>
  <style>
    body { font-family: sans-serif; padding: 16px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 6px; font-size: 13px; }
    th { background: #f5f5f5; position: sticky; top: 0; }
    .critical { background: #ffe0e0; }
    .warning { background: #fff3cd; }
    .info { background: #e7f3ff; }
  </style>
</head>
<body>
  <h3>Alerts (last 50, auto-refresh 5s)</h3>
  <div id="status"></div>
  <table id="alerts">
    <thead>
      <tr>
        <th>ID</th><th>Type</th><th>Status</th><th>Severity</th><th>LogID</th><th>Reason</th><th>Message</th><th>Created</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
  <script>
    async function loadAlerts() {
      try {
        const res = await fetch('/alerts?limit=50');
        const data = await res.json();
        const tbody = document.querySelector('#alerts tbody');
        tbody.innerHTML = '';
        data.forEach(a => {
          const tr = document.createElement('tr');
          if (a.severity) tr.className = a.severity;
          tr.innerHTML = `
            <td>${a.id}</td>
            <td>${a.alert_type}</td>
            <td>${a.status}</td>
            <td>${a.severity || ''}</td>
            <td>${a.log_id}</td>
            <td>${a.anomaly_reason || ''}</td>
            <td>${(a.message || '').slice(0,180)}</td>
            <td>${a.created_at || ''}</td>
          `;
          tbody.appendChild(tr);
        });
        document.getElementById('status').textContent = `Loaded ${data.length} alerts`;
      } catch (e) {
        document.getElementById('status').textContent = 'Error loading alerts';
      }
    }
    loadAlerts();
    setInterval(loadAlerts, 5000);
  </script>
</body>
</html>
"""
            self.wfile.write(html.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def serve(db_path: str, host: str, port: int):
    server = ThreadingHTTPServer((host, port), AlertHandler)
    server.db_path = db_path
    print(f"Serving alerts on http://{host}:{port}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Simple alerts viewer server")
    parser.add_argument("--db", default="db/monitor.db", help="Path to SQLite DB")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()
    serve(args.db, args.host, args.port)


if __name__ == "__main__":
    main()

