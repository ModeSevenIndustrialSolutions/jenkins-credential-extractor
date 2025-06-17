# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Tests for Jenkins automation functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jenkins_credential_extractor.jenkins import JenkinsAutomation
from jenkins_credential_extractor.auth import JenkinsAuthManager
from jenkins_credential_extractor.config import JenkinsConfigManager
from jenkins_credential_extractor.error_handling import AuthenticationError, NetworkError


class TestJenkinsAutomation:
    """Test cases for JenkinsAutomation."""

    @pytest.fixture
    def automation(self):
        """Create a test automation instance."""
        return JenkinsAutomation(
            jenkins_url="https://jenkins.example.com", jenkins_ip="192.168.1.100"
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

    @patch("jenkins_credential_extractor.jenkins.JenkinsAuthManager")
    def test_ensure_authentication_success(self, mock_auth_manager, automation):
        """Test successful authentication."""
        mock_session = Mock(spec=requests.Session)
        mock_auth_manager.return_value.get_authenticated_session.return_value = (
            mock_session
        )
        mock_auth_manager.return_value.is_authenticated.return_value = True

        automation.auth_manager = mock_auth_manager.return_value

        result = automation.ensure_authentication()
        assert result is True
        assert automation.session is not None

    @patch("jenkins_credential_extractor.jenkins.JenkinsAuthManager")
    def test_ensure_authentication_failure(self, mock_auth_manager, automation):
        """Test authentication failure."""
        mock_auth_manager.return_value.get_authenticated_session.return_value = None
        mock_auth_manager.return_value.is_authenticated.return_value = False

        automation.auth_manager = mock_auth_manager.return_value

        result = automation.ensure_authentication()
        assert result is False
        assert automation.session is None

    def test_batch_size_selection(self, automation):
        """Test automatic batch size selection."""
        # Test small batch
        result = automation._select_processing_method([("user1", "pass1")])
        assert result == "sequential"

        # Test medium batch
        credentials = [("user" + str(i), "pass" + str(i)) for i in range(25)]
        result = automation._select_processing_method(credentials)
        assert result == "parallel"

        # Test large batch
        credentials = [("user" + str(i), "pass" + str(i)) for i in range(100)]
        result = automation._select_processing_method(credentials)
        assert result == "optimized"

    def test_thread_calculation(self, automation):
        """Test optimal thread count calculation."""
        # Test small credential count
        result = automation._calculate_optimal_threads(5)
        assert result <= 3

        # Test medium credential count
        result = automation._calculate_optimal_threads(25)
        assert result <= 10

        # Test large credential count
        result = automation._calculate_optimal_threads(100)
        assert result <= 20

    @patch("jenkins_credential_extractor.jenkins.requests.Session")
    def test_validate_jenkins_access_success(self, mock_session_class, automation):
        """Test successful Jenkins access validation."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<form><input name="Jenkins-Crumb" value="test"></form>'
        mock_session.get.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager.is_authenticated = Mock(return_value=True)

        result = automation.validate_jenkins_access()
        assert result is True

    @patch("jenkins_credential_extractor.jenkins.requests.Session")
    def test_validate_jenkins_access_failure(self, mock_session_class, automation):
        """Test Jenkins access validation failure."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_session.get.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager.is_authenticated = Mock(return_value=True)

        result = automation.validate_jenkins_access()
        assert result is False

    def test_check_script_console_permissions_success(self, automation):
        """Test script console permissions check - success."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<form><input name="Jenkins-Crumb" value="test"></form>'
        mock_session.get.return_value = mock_response

        automation.session = mock_session

        result = automation._check_script_console_permissions()
        assert result is True

    def test_check_script_console_permissions_forbidden(self, automation):
        """Test script console permissions check - forbidden."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_session.get.return_value = mock_response

        automation.session = mock_session

        result = automation._check_script_console_permissions()
        assert result is False

    @patch("jenkins_credential_extractor.jenkins.requests.Session")
    def test_decrypt_single_password_success(self, mock_session_class, automation):
        """Test successful password decryption."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<h2>Result</h2><pre>decrypted_password</pre>'
        mock_session.post.return_value = mock_response
        mock_session.get.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = mock_session
        automation.auth_manager.is_authenticated.return_value = True

        result = automation.decrypt_single_password("{test_encrypted_password}")
        assert result == "decrypted_password"

    @patch("jenkins_credential_extractor.jenkins.requests.Session")
    def test_decrypt_single_password_failure(self, mock_session_class, automation):
        """Test password decryption failure."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_session.post.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = mock_session
        automation.auth_manager.is_authenticated.return_value = True

        with pytest.raises(AuthenticationError):
            automation.decrypt_single_password("{test_encrypted_password}")

    def test_batch_decrypt_passwords_intelligently_small_batch(self, automation):
        """Test intelligent batch processing for small credential sets."""
        credentials = [("user1", "pass1"), ("user2", "pass2")]

        # Mock the individual decryption methods
        automation.batch_decrypt_passwords = Mock(return_value=credentials)

        result = automation.batch_decrypt_passwords_intelligently(credentials)

        # Should use legacy/manual method for small batches
        automation.batch_decrypt_passwords.assert_called_once_with(credentials)
        assert result == credentials

    @patch("jenkins_credential_extractor.jenkins.console")
    def test_batch_decrypt_passwords_intelligently_large_batch(self, mock_console, automation):
        """Test intelligent batch processing for large credential sets."""
        # Create a large set of credentials (100+)
        credentials = [("user" + str(i), "pass" + str(i)) for i in range(100)]
        expected_result = [("user" + str(i), "decrypted" + str(i)) for i in range(100)]

        # Mock the optimized batch method
        automation.batch_decrypt_passwords_optimized = Mock(return_value=expected_result)
        automation.ensure_authentication = Mock(return_value=True)

        result = automation.batch_decrypt_passwords_intelligently(credentials)

        # Should use optimized method for large batches
        automation.batch_decrypt_passwords_optimized.assert_called_once_with(credentials)
        assert result == expected_result

    @patch("jenkins_credential_extractor.jenkins.console")
    def test_batch_decrypt_passwords_intelligently_medium_batch(self, mock_console, automation):
        """Test intelligent batch processing for medium credential sets."""
        # Create a medium set of credentials (25)
        credentials = [("user" + str(i), "pass" + str(i)) for i in range(25)]
        expected_result = [("user" + str(i), "decrypted" + str(i)) for i in range(25)]

        # Mock the parallel method
        automation.batch_decrypt_passwords_parallel = Mock(return_value=expected_result)
        automation.ensure_authentication = Mock(return_value=True)

        result = automation.batch_decrypt_passwords_intelligently(credentials)

        # Should use parallel method for medium batches
        automation.batch_decrypt_passwords_parallel.assert_called_once_with(credentials)
        assert result == expected_result

    @patch("subprocess.run")
    def test_download_credentials_file_success(self, mock_subprocess, automation):
        """Test successful credentials file download."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        result = automation.download_credentials_file("test_credentials.xml")

        assert result is True
        mock_subprocess.assert_called_once()

    @patch("subprocess.run")
    def test_download_credentials_file_failure(self, mock_subprocess, automation):
        """Test credentials file download failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"
        mock_subprocess.return_value = mock_result

        result = automation.download_credentials_file("test_credentials.xml")

        assert result is False

    def test_csrf_token_extraction(self, automation):
        """Test CSRF token extraction from HTML."""
        html_with_token = '<input name="Jenkins-Crumb" value="test-csrf-token">'
        automation.session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_with_token
        automation.session.get.return_value = mock_response

        token = automation._get_csrf_token()
        assert token == "test-csrf-token"

    def test_csrf_token_extraction_alternative(self, automation):
        """Test alternative CSRF token extraction."""
        html_with_token = '{"crumb":"alternative-csrf-token"}'
        automation.session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_with_token
        automation.session.get.return_value = mock_response

        token = automation._get_csrf_token()
        assert token == "alternative-csrf-token"

    def test_csrf_token_extraction_none(self, automation):
        """Test CSRF token extraction when none found."""
        html_without_token = '<html><body>No token here</body></html>'
        automation.session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_without_token
        automation.session.get.return_value = mock_response

        token = automation._get_csrf_token()
        assert token is None

    def test_script_result_extraction(self, automation):
        """Test script execution result extraction."""
        html_with_result = '<h2>Result</h2><pre>test_result_value</pre>'

        result = automation._extract_script_result(html_with_result)
        assert result == "test_result_value"

    def test_script_result_extraction_alternative(self, automation):
        """Test alternative script result extraction."""
        html_with_result = '<div class="console-output">alternative_result</div>'

        result = automation._extract_script_result(html_with_result)
        assert result == "alternative_result"

    def test_script_result_extraction_none(self, automation):
        """Test script result extraction when none found."""
        html_without_result = '<html><body>No result here</body></html>'

        result = automation._extract_script_result(html_without_result)
        assert result is None

    @patch("jenkins_credential_extractor.jenkins.requests.get")
    def test_test_jenkins_connectivity_success(self, mock_get, automation):
        """Test successful Jenkins connectivity test."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = automation.test_jenkins_connectivity()
        assert result is True

    @patch("jenkins_credential_extractor.jenkins.requests.get")
    def test_test_jenkins_connectivity_failure(self, mock_get, automation):
        """Test failed Jenkins connectivity test."""
        mock_get.side_effect = requests.exceptions.RequestException("Connection failed")

        result = automation.test_jenkins_connectivity()
        assert result is False

    def test_save_credentials_file_success(self, automation, tmp_path):
        """Test successful credentials file saving."""
        test_file = tmp_path / "test_credentials.txt"
        credentials = [("user1", "pass1"), ("user2", "pass2")]

        result = automation.save_credentials_file(credentials, str(test_file))

        assert result is True
        assert test_file.exists()

        # Verify file content
        content = test_file.read_text()
        assert "user1=pass1" in content
        assert "user2=pass2" in content

    def test_get_jenkins_info_success(self, automation):
        """Test successful Jenkins info retrieval."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"mode": "NORMAL", "nodeDescription": "Test Jenkins"}
        mock_session.get.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = mock_session
        automation.auth_manager.is_authenticated.return_value = True

        result = automation.get_jenkins_info()

        assert result is not None
        assert result["mode"] == "NORMAL"
        assert result["nodeDescription"] == "Test Jenkins"

    def test_get_jenkins_info_failure(self, automation):
        """Test Jenkins info retrieval failure."""
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = None
        automation.auth_manager.is_authenticated.return_value = False

        result = automation.get_jenkins_info()
        assert result is None


class TestJenkinsAutomationIntegration:
    """Integration tests for Jenkins automation."""

    @pytest.fixture
    def automation_with_auth(self):
        """Create automation instance with mocked authentication."""
        automation = JenkinsAutomation(
            jenkins_url="https://jenkins.example.com",
            jenkins_ip="192.168.1.100"
        )

        # Mock the auth manager
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = Mock()
        automation.auth_manager.is_authenticated.return_value = True

        return automation

    def test_end_to_end_password_decryption_flow(self, automation_with_auth):
        """Test complete password decryption workflow."""
        # Setup mock session
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<h2>Result</h2><pre>decrypted_password</pre>'
        mock_session.post.return_value = mock_response
        mock_session.get.return_value = mock_response

        automation_with_auth.session = mock_session

        # Test single password decryption
        result = automation_with_auth.decrypt_single_password("{encrypted_password}")
        assert result == "decrypted_password"

    def test_authentication_session_sharing(self, automation_with_auth):
        """Test that authentication sessions are properly shared."""
        # This tests the main issue mentioned in the conversation
        # The automation should use the auth manager's session, not create its own

        mock_session = Mock()
        automation_with_auth.auth_manager.get_authenticated_session.return_value = mock_session

        # When ensuring authentication, it should use the auth manager's session
        result = automation_with_auth.ensure_authentication()

        assert result is True
        assert automation_with_auth.session is mock_session
        automation_with_auth.auth_manager.get_authenticated_session.assert_called()


class TestJenkinsAutomationErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def automation(self):
        """Create a test automation instance."""
        return JenkinsAutomation(
            jenkins_url="https://jenkins.example.com", jenkins_ip="192.168.1.100"
        )

    def test_network_error_handling(self, automation):
        """Test network error handling during decryption."""
        mock_session = Mock()
        mock_session.post.side_effect = requests.exceptions.RequestException("Network error")

        automation.session = mock_session
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = mock_session
        automation.auth_manager.is_authenticated.return_value = True

        with pytest.raises(NetworkError):
            automation.decrypt_single_password("{encrypted_password}")

    def test_authentication_error_handling(self, automation):
        """Test authentication error handling."""
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = None
        automation.auth_manager.is_authenticated.return_value = False

        result = automation.ensure_authentication()
        assert result is False

    def test_script_console_permission_error(self, automation):
        """Test script console permission error handling."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_session.post.return_value = mock_response

        automation.session = mock_session
        automation.auth_manager = Mock()
        automation.auth_manager.get_authenticated_session.return_value = mock_session
        automation.auth_manager.is_authenticated.return_value = True

        with pytest.raises(AuthenticationError):
            automation.decrypt_single_password("{encrypted_password}")
