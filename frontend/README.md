# frontend/

The web page for operators and partners (Ayuntamiento). Served by the FastAPI back end (same server as the API). One shared login.

Shows: charts and live gauges, station status, progress towards the next plant, today's conditions level, analytics report, a map of the station and Bilbao green spaces, settings, and a manual unlock button.

- Charts and gauges: **Apache ECharts**. The ECharts file is kept in this folder, not loaded from a CDN.
- Data: only from the back end's REST endpoints (JSON). The page never talks to MQTT or the database.
- Refresh: every 10 s, set by `REFRESH_SECONDS` at the top of the page script. Charts show the last 24 h by default (picker: 24 h / 7 d / 30 d).
- Map library: still open, see [#46](https://github.com/marieashtonkoehl/IoT_final_project_2026/issues/46).

Endpoints → [docs/architecture.md](../docs/architecture.md#rest-endpoints).
