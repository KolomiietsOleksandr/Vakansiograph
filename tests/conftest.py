"""
Pytest configuration and fixtures
"""

import pytest
from app import create_app


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    app = create_app(config_name="testing")
    return app


@pytest.fixture
def client(app):
    """Create Flask test client"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create Flask CLI test runner"""
    return app.test_cli_runner()
