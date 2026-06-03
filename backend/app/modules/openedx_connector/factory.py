from app.core.config import settings
from app.modules.openedx_connector.base import OpenEdXConnector
from app.modules.openedx_connector.mock import MockOpenEdXConnector
from app.modules.openedx_connector.real import RealOpenEdXConnector


def get_openedx_connector() -> OpenEdXConnector:
    if settings.use_mock_openedx:
        return MockOpenEdXConnector()
    return RealOpenEdXConnector()
