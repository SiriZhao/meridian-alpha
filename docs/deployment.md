# Deployment direction

## Required production properties

Containerize the tool-only MCP service behind HTTPS, authenticate every
sensitive endpoint, use environment/secret-manager injection only, emit
structured logs, keep raw account data non-persistent, and expose `/health`.
No brokerage credentials belong in the service.

| Option | Cost profile | Complexity | Fit |
| --- | --- | --- | --- |
| Fly.io / Render-style managed container | low for an always-on small instance | low | simplest persistent prototype after auth/TLS configuration |
| Cloud Run-style serverless container | low at sparse traffic | medium | good scale-to-zero behavior; requires cloud account and ingress/auth setup |

No provider has been selected or deployed because that would create an external
service and potentially cost without a user-approved cloud account and domain.
For local development run `python -m uv run python -c "from meridian.mcp_server import main; main()"`.
For ChatGPT Developer Mode, expose the local `/mcp` endpoint via a user-approved
HTTPS tunnel, then add the HTTPS URL as an app in ChatGPT settings.
