# Open edX Real Integration

The AI Server uses a connector adapter to avoid coupling the whole system to a specific Open edX release.

## Modes

```env
USE_MOCK_OPENEDX=true   # demo mode
USE_MOCK_OPENEDX=false  # real Open edX mode
```

## Required settings

```env
OPENEDX_BASE_URL=https://your-openedx.example.edu
OPENEDX_CLIENT_ID=...
OPENEDX_CLIENT_SECRET=...
OPENEDX_COURSE_BLOCKS_PATH=/api/courses/v2/blocks/
OPENEDX_PUBLISH_ENDPOINT=/api/ai-connector/v1/courses/{course_id}/problems
```

## Connector responsibilities
- Read course outline/blocks.
- Normalize HTML/video/transcript/problem/file metadata into internal block format.
- Publish approved OLX problem back into Open edX through the connector plugin endpoint.

## Why adapter pattern?
Different Tutor/Open edX versions may expose slightly different APIs. Only `RealOpenEdXConnector` should change when the Open edX endpoint differs.
