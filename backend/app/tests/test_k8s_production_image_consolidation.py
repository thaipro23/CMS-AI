from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SERVICES = ('runtime-init', 'migrate', 'backend', 'worker', 'worker-heavy', 'worker-analytics', 'beat')


def test_compose_builds_only_two_custom_images():
    compose = yaml.safe_load((ROOT / 'docker-compose.prod.yml').read_text(encoding='utf-8'))
    services = compose['services']
    built = {name for name, service in services.items() if service.get('build')}
    assert built == {'backend', 'frontend'}
    backend_image = services['backend']['image']
    assert backend_image.startswith('${BACKEND_IMAGE:-ai-server-backend:')
    for name in BACKEND_SERVICES:
        assert services[name]['image'] == backend_image
    assert services['frontend']['image'].startswith('${FRONTEND_IMAGE:-ai-server-frontend:')


def test_k8s_workloads_use_only_backend_and_frontend_application_images():
    images = []
    for path in (ROOT / 'deploy/k8s').rglob('*.yaml'):
        for doc in yaml.safe_load_all(path.read_text(encoding='utf-8')):
            if not isinstance(doc, dict):
                continue
            spec = doc.get('spec') or {}
            pod_spec = None
            if doc.get('kind') == 'Deployment':
                pod_spec = ((spec.get('template') or {}).get('spec') or {})
            elif doc.get('kind') == 'Job':
                pod_spec = (((spec.get('template') or {}).get('spec')) or {})
            if pod_spec:
                images.extend(c.get('image') for c in pod_spec.get('containers', []) if c.get('image'))
    assert images
    assert all('ai-server-backend' in image or 'ai-server-frontend' in image for image in images)


def test_production_build_context_excludes_non_runtime_payload():
    dockerignore = (ROOT / '.dockerignore').read_text(encoding='utf-8')
    for marker in ('backend/app/tests', 'docs', 'e2e', 'frontend-app-learning-patch', '*.pem', '*.key', '*.log'):
        assert marker in dockerignore


def test_no_raster_evidence_or_private_key_is_shipped():
    raster = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    assert not [p for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower() in raster]
    assert not [p for p in ROOT.rglob('*') if p.is_file() and p.suffix.lower() in {'.pem', '.key'}]
