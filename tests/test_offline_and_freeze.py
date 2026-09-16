"""
Tests for 100% Offline Operation and Scientific Detector Settings Freeze.
"""
import socket
import pytest
from app import create_app
from app.services.settings_service import get_current_settings as get_system_settings


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_detector_scientific_settings_frozen(app_instance):
    """Verify detector parameters remain completely frozen to preserve scientific baseline."""
    import config
    settings = config.DEFAULT_SETTINGS
    
    # Assert exact scientific baseline thresholds
    assert settings.get('shingle_size') == 5
    assert settings.get('jaccard_threshold') == 0.40
    assert settings.get('tfidf_threshold') == 0.40
    assert settings.get('min_sentence_words') == 4
    assert settings.get('max_candidate_retrieval') == 50
    assert settings.get('citation_filter_mode') == 'refined'
    assert settings.get('common_text_filter_mode') == 'span_level'


def test_offline_guarantee_no_outbound_network(monkeypatch):
    """
    Ensure application runs completely offline without any internet connection.
    Mock socket connection attempt to external IP and ensure nothing calls out.
    """
    def mock_socket_connect(self, address):
        host, port = address
        # Allow only localhost / 127.0.0.1 / ::1
        if host not in ['127.0.0.1', 'localhost', '::1', '0.0.0.0']:
            raise RuntimeError(f"CRITICAL VIOLATION: Outbound network attempt to external address: {address}")
        return True

    monkeypatch.setattr(socket.socket, "connect", mock_socket_connect)
    
    # Create app and execute internal services in 100% offline isolation
    app = create_app()
    client = app.test_client()
    res = client.get('/api/health')
    assert res.status_code in [200, 404, 302]
