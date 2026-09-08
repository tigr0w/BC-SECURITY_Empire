# CORS Allowed Origins

By default, Empire's REST API and Socket.IO server accept requests from any origin (`*`). The `cors_origins` setting lets operators restrict cross-origin access to a specific list of origins.

## Configuration

Set `cors_origins` under the `api` block in `config.yaml`:

```yaml
api:
  ip: 0.0.0.0
  port: 1337
  secure: false
  cors_origins:
    - "http://localhost:8080"
    - "https://starkiller.example.com"
```

If the key is omitted, the default is `["*"]` (allow all origins), which preserves the historical behavior.

## Environment Variable Override

Override the list at runtime without editing `config.yaml` by setting `EMPIRE_API__CORS_ORIGINS` to a JSON-encoded array:

```bash
EMPIRE_API__CORS_ORIGINS='["https://starkiller.example.com","http://localhost:8080"]' ./ps-empire server
```

## Notes

- Both the REST middleware and the Socket.IO server read from the same `cors_origins` list.
- A list containing `"*"` is treated as allow-all by both Starlette and the Socket.IO server — no special-casing is required.
- Restricting origins does not replace authentication; it is a browser-side enforcement layer only.
