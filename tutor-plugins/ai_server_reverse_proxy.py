"""Tutor Caddy reverse proxy for the external AI Learning Server containers.

This plugin only adds Caddy site blocks. It does not run the AI Server. The
AI Server must be started separately with docker-compose.prod.yml and must join
Tutor's Docker network, usually tutor_local_default.

Install on the Tutor/Open edX server:
  cp tutor-plugins/ai_server_reverse_proxy.py "$(tutor plugins printroot)/ai_server_reverse_proxy.py"
  tutor plugins enable ai_server_reverse_proxy
  tutor config save \
    --set AI_SERVER_FRONTEND_HOST=ai.cms-test.poly.edu.vn \
    --set AI_SERVER_API_HOST=api-ai.cms-test.poly.edu.vn
  tutor local restart caddy
"""

from tutor import hooks

hooks.Filters.CONFIG_DEFAULTS.add_items(
    [
        ("AI_SERVER_FRONTEND_HOST", "ai.cms-test.poly.edu.vn"),
        ("AI_SERVER_API_HOST", "api-ai.cms-test.poly.edu.vn"),
        ("AI_SERVER_FRONTEND_UPSTREAM", "ai-frontend:3000"),
        ("AI_SERVER_API_UPSTREAM", "ai-backend:8000"),
    ]
)

hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile",
        r'''
# AI Learning Server reverse proxy. AI containers are external to Tutor but share the Tutor Docker network.
{{ AI_SERVER_FRONTEND_HOST }} {
    reverse_proxy {{ AI_SERVER_FRONTEND_UPSTREAM }}
}

{{ AI_SERVER_API_HOST }} {
    reverse_proxy {{ AI_SERVER_API_UPSTREAM }}
}
''',
    )
)
