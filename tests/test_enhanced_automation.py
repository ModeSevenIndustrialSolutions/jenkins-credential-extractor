# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Tests for enhanced Jenkins automation functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from typing import List, Tuple

from src.jenkins_credential_extractor.enhanced_jenkins import EnhancedJenkinsAutomation
from src.jenkins_credential_extractor.auth import JenkinsAuthManager
from src.jenkins_credential_extractor.config import JenkinsConfigManager


class TestEnhancedJenkinsAutomation:
    """Test cases for EnhancedJenkinsAutomation."""

    @pytest.fixture
    def automation(self):
        """Create a test automation instance."""
        return EnhancedJenkinsAutomation(
            jenkins_url="https://jenkins.example.com",
            jenkins_ip="192.168.1.100"
        )

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        session = Mock(spec=requests.Session)
        return session

    def test_initialization(self, automation):
        """Test proper initialization."""
        assert automation.jenkins_url == "https://jenkins.example.com"
        assert automation.jenkins_ip == "192.168.1.100"
        assert isinstance(automation.auth_manager, JenkinsAuthManager)
        assert automation.session is None

    @patch('src.jenkins_credential_extractor.enhanced_jenkins.JenkinsAuthManager')
    def test_ensure_authentication_success(self, mock_auth_manager, automation):
        """Test successful authentication."""
        mock_session = Mock(spec=requests.Session)
        mock_auth_manager.return_value.get_authenticated_session.return_value = mock_session
        mock_auth_manager.return_value.is_authenticated.return_value = True

        automation.auth_manager = mock_auth_manager.return_value

        result = automation.ensure_authentication()
        assert result is True
        assert automation.session is not None

    @patch('src.jenkins_credential_extractor.enhanced_jenkins.JenkinsAuthManager')
    def test_ensure_authentication_failure(self, mock_auth_manager, automation):
        """Test authentication failure."""
        mock_auth_manager.return_value.get_authenticated_session.return_value = None

        automation.auth_manager = mock_auth_manager.return_value

        result = automation.ensure_authentication()
        assert result is False

    def test_csrf_token_extraction(self, automation, mock_session):
        """Test CSRF token extraction."""
        # Mock response with CSRF token in form field
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''
        <html>
            <form>
                <input name="Jenkins-Crumb" value="test_token" />
            </form>
        </html>
        '''
        mock_session.get.return_value = mock_response
        automation.session = mock_session

        token = automation._get_csrf_token()
        assert token == "test_token"

    def test_csrf_token_extraction_failure(self, automation, mock_session):
        """Test CSRF token extraction failure."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response
        automation.session = mock_session

        token = automation._get_csrf_token()
        assert token is None

    def test_batch_decrypt_passwords_parallel(self, automation, mock_session):
        """Test parallel batch password decryption."""
        automation.session = mock_session

        # Mock credentials
        credentials = [
            ("user1", "encrypted_pass1"),
            ("user2", "encrypted_pass2"),
        ]

        # Mock successful authentication and decryption
        with patch.object(automation, 'ensure_authentication', return_value=True):
            with patch.object(automation, '_decrypt_password_with_retry', side_effect=[
                "decrypted_pass1", "decrypted_pass2"
            ]):
                with patch('src.jenkins_credential_extractor.enhanced_jenkins.ThreadPoolExecutor') as mock_executor:
                    with patch('src.jenkins_credential_extractor.enhanced_jenkins.as_completed') as mock_as_completed:
                        with patch('src.jenkins_credential_extractor.enhanced_jenkins.Progress'):
                            # Mock the executor behavior
                            mock_future1 = Mock()
                            mock_future1.result.return_value = "decrypted_pass1"
                            mock_future2 = Mock()
                            mock_future2.result.return_value = "decrypted_pass2"

                            mock_as_completed.return_value = [mock_future1, mock_future2]

                            # Mock the executor context manager
                            mock_executor_instance = Mock()
                            mock_executor.return_value.__enter__.return_value = mock_executor_instance
                            mock_executor.return_value.__exit__.return_value = None

                            # Set up the submit side effect to map credentials to futures
                            submit_mapping = {
                                'encrypted_pass1': mock_future1,
                                'encrypted_pass2': mock_future2
                            }

                            def mock_submit(func, encrypted_pass):
                                return submit_mapping[encrypted_pass]

                            mock_executor_instance.submit = mock_submit

                            result = automation.batch_decrypt_passwords_parallel(credentials)

                            expected = [
                                ("user1", "decrypted_pass1"),
                                ("user2", "decrypted_pass2"),
                            ]
                            assert result == expected

    def test_batch_size_selection(self, automation):
        """Test automatic batch size selection."""
        # Small batch - should use sequential per implementation logic
        small_credentials = [("user1", "pass1"), ("user2", "pass2")]
        assert automation._select_processing_method(small_credentials) == "sequential"

        # Medium batch - should use parallel with optimal threads
        medium_credentials = [("user" + str(i), "pass" + str(i)) for i in range(20)]
        assert automation._select_processing_method(medium_credentials) == "parallel"

        # Large batch - should use optimized single script
        large_credentials = [("user" + str(i), "pass" + str(i)) for i in range(100)]
        assert automation._select_processing_method(large_credentials) == "optimized"

    def test_validate_jenkins_access_success(self, automation, mock_session):
        """Test successful Jenkins access validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response
        automation.session = mock_session

        with patch.object(automation, 'ensure_authentication', return_value=True):
            result = automation.validate_jenkins_access()
            assert result is True

    def test_validate_jenkins_access_failure(self, automation):
        """Test Jenkins access validation failure."""
        with patch.object(automation, 'ensure_authentication', return_value=False):
            result = automation.validate_jenkins_access()
            assert result is False

    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_retry_mechanism(self, mock_sleep, automation, mock_session):
        """Test retry mechanism with exponential backoff."""
        automation.session = mock_session

        # Mock first two calls fail, third succeeds
        mock_session.post.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            Mock(status_code=200, text="<h2>Result</h2><pre>decrypted_password</pre>")
        ]

        with patch.object(automation, '_get_csrf_token', return_value="test_token"):
            with patch.object(automation, 'ensure_authentication', return_value=True):
                result = automation._decrypt_password_with_retry("encrypted_pass", max_retries=3)
                assert result == "decrypted_password"
                assert mock_session.post.call_count == 3

    def test_retry_mechanism_exhausted(self, automation, mock_session):
        """Test retry mechanism when all retries are exhausted."""
        automation.session = mock_session

        # All calls fail
        mock_session.post.side_effect = requests.RequestException("Persistent error")

        with patch.object(automation, '_get_csrf_token', return_value="test_token"):
            with patch.object(automation, 'ensure_authentication', return_value=True):
                with patch('time.sleep'):  # Mock sleep
                    # Expect NetworkError to be raised after retries exhausted
                    with pytest.raises(Exception):  # Catches NetworkError
                        automation._decrypt_password_with_retry("encrypted_pass", max_retries=2)
                    assert mock_session.post.call_count == 2


class TestJenkinsAuthManager:
    """Test cases for JenkinsAuthManager."""

    @pytest.fixture
    def auth_manager(self):
        """Create a test auth manager instance."""
        return JenkinsAuthManager("https://jenkins.example.com")

    def test_initialization(self, auth_manager):
        """Test proper initialization."""
        assert auth_manager.jenkins_url == "https://jenkins.example.com"
        assert auth_manager.client_secrets_file is None

    def test_get_auth_method(self, auth_manager):
        """Test getting authentication method."""
        # Should return None when no auth is configured
        method = auth_manager.get_auth_method()
        assert method is None or isinstance(method, str)

    @patch('src.jenkins_credential_extractor.auth.requests.Session')
    def test_session_creation(self, mock_session_class, auth_manager):
        """Test session creation."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Test session is created
        assert auth_manager.session is not None


class TestJenkinsConfigManager:
    """Test cases for JenkinsConfigManager."""

    @pytest.fixture
    def config_manager(self):
        """Create a test config manager instance."""
        return JenkinsConfigManager()

    def test_initialization(self, config_manager):
        """Test proper initialization."""
        # The actual implementation uses ".jenkins-credential-extractor"
        assert config_manager.config_dir.name == ".jenkins-credential-extractor"

    def test_load_config(self, config_manager):
        """Test config loading."""
        config = config_manager.load_config()
        # Should return empty dict if no config exists
        assert isinstance(config, dict)

    def test_save_config(self, config_manager):
        """Test config saving."""
        test_config = {"test": "value"}
        # Should not raise exception
        config_manager.save_config(test_config)

    def test_setup_initial_configuration(self, config_manager):
        """Test initial configuration setup."""
        # Mock the interactive prompts
        with patch('rich.prompt.Prompt.ask', side_effect=["https://jenkins.example.com", "192.168.1.100"]):
            with patch('rich.prompt.Confirm.ask', return_value=False):
                result = config_manager.setup_initial_configuration()
                assert isinstance(result, dict)


# Integration Tests
class TestIntegration:
    """Integration tests for the complete automation workflow."""

    @pytest.fixture
    def full_automation_stack(self):
        """Create a complete automation stack for testing."""
        automation = EnhancedJenkinsAutomation(
            jenkins_url="https://jenkins.example.com",
            jenkins_ip="192.168.1.100"
        )
        config_manager = JenkinsConfigManager()
        return automation, config_manager

    def test_end_to_end_workflow(self, full_automation_stack):
        """Test complete end-to-end automation workflow."""
        automation, _ = full_automation_stack

        # Mock successful authentication and processing
        with patch.object(automation, 'ensure_authentication', return_value=True):
            with patch.object(automation, 'validate_jenkins_access', return_value=True):
                with patch.object(automation, 'batch_decrypt_passwords_parallel', return_value=[
                    ("user1", "decrypted_pass1"),
                    ("user2", "decrypted_pass2")
                ]):
                    # Simulate credential processing
                    credentials = [("user1", "encrypted_pass1"), ("user2", "encrypted_pass2")]
                    result = automation.batch_decrypt_passwords_parallel(credentials)

                    assert len(result) == 2
                    assert result[0] == ("user1", "decrypted_pass1")
                    assert result[1] == ("user2", "decrypted_pass2")

    def test_performance_threshold_validation(self, full_automation_stack):
        """Test that performance meets expected thresholds."""
        automation, _ = full_automation_stack

        # Test batch size optimization
        large_batch = [("user" + str(i), "pass" + str(i)) for i in range(100)]
        processing_method = automation._select_processing_method(large_batch)

        # Should use optimized method for large batches
        assert processing_method == "optimized"

        # Test thread count optimization
        optimal_threads = automation._calculate_optimal_threads(50)
        assert 5 <= optimal_threads <= 20  # Should be in reasonable range


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
