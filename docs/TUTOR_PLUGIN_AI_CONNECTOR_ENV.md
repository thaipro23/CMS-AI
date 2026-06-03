# Tutor plugin: AI Connector env/settings injection

This release includes a single-file Tutor plugin:

```text
tutor-plugins/ai_learning_connector_env.py
```

It avoids editing:

```text
$(tutor config printroot)/env/local/docker-compose.override.yml
```

Instead, it writes the `AI_CONNECTOR_*` values into generated CMS Django settings via Tutor's `openedx-cms-common-settings` patch. The connector still accepts real process environment variables, but it can now also read the same values from Django settings.

## Why this is needed

AI Server and Open edX are separate systems. The AI Server reads:

```env
OPENEDX_CONNECTOR_HMAC_SECRET=...
```

The CMS/Studio connector must read the same value as:

```env
AI_CONNECTOR_HMAC_SECRET=...
```

The plugin stores that `AI_CONNECTOR_HMAC_SECRET` on the Tutor/Open edX side.

## Install on the Open edX/Tutor server

From the AI project folder or after copying the plugin file to the Open edX server:

```bash
mkdir -p "$(tutor plugins printroot)"
cp tutor-plugins/ai_learning_connector_env.py "$(tutor plugins printroot)/ai_learning_connector_env.py"
tutor plugins enable ai_learning_connector_env
```

Set the values. `AI_CONNECTOR_HMAC_SECRET` must be exactly the same as `OPENEDX_CONNECTOR_HMAC_SECRET` in the AI Server `.env.production`.

```bash
tutor config save \
  --set AI_CONNECTOR_PUBLISH_USERNAME=admin \
  --set AI_CONNECTOR_ALLOW_ANONYMOUS_PUBLISH=false \
  --set AI_CONNECTOR_HMAC_SECRET='PASTE_THE_SAME_HMAC_SECRET_AS_AI_SERVER' \
  --set AI_CONNECTOR_HMAC_SKEW_SECONDS=300 \
  --set AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS='scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn' \
  --set AI_CONNECTOR_COMPONENT_PUBLISH_ENABLED=false \
  --set AI_CONNECTOR_TAGGING_ENABLED=true \
  --set AI_CONNECTOR_TAG_TAXONOMY_EXPORT_ID=ai-learning-check \
  --set AI_CONNECTOR_TAG_TAXONOMY_NAME='AI Learning Check'
```

Restart CMS services:

```bash
tutor local restart cms cms-worker
```

## Verify

Check the generated CMS settings:

```bash
grep -R "AI_CONNECTOR_HMAC_SECRET" "$(tutor config printroot)/env/apps/openedx/settings/cms"
```

Check from inside CMS Django shell:

```bash
tutor local run cms ./manage.py cms shell -c "from django.conf import settings; print(bool(getattr(settings, 'AI_CONNECTOR_HMAC_SECRET', ''))); print(getattr(settings, 'AI_CONNECTOR_ALLOWED_DOWNLOAD_HOSTS', ''))"
```

Expected output:

```text
True
scms-test.poly.edu.vn,cms-test.poly.edu.vn,app.cms-test.poly.edu.vn
```

## Important

This Tutor plugin only injects configuration. It does not install the Django package `openedx_ai_connector`. Keep using your current connector installation/build process for the plugin package itself.
