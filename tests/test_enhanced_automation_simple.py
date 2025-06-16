# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Simplified tests for enhanced Jenkins automation functionality."""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jenkins_credential_extractor.enhanced_jenkins import EnhancedJenkinsAutomation
from jenkins_credential_extractor.auth import JenkinsAuthManager


class TestEnhancedJenkinsAutomationSimple:
    """Simple test cases for EnhancedJenkinsAutomation."""

    @pytest.fixture
    def automation(self):
        """Create a test automation instance."""
        return EnhancedJenkinsAutomation(
            jenkins_url="https://jenkins.example.com",
            jenkins_ip="192.168.1.100"
        )

    def test_initialization(self, automation):
        """Test proper initialization."""
        assert automation.jenkins_url == "https://jenkins.example.com"
        assert automation.jenkins_ip == "192.168.1.100"
        assert isinstance(automation.auth_manager, JenkinsAuthManager)
        assert automation.session is None

    @patch('jenkins_credential_extractor.enhanced_jenkins.JenkinsAuthManager')
    def test_ensure_authentication_success(self, mock_auth_manager, automation):
        """Test successful authentication."""
        mock_session = Mock()
        mock_auth_manager.return_value.get_authenticated_session.return_value = mock_session
        mock_auth_manager.return_value.is_authenticated.return_value = True

        automation.auth_manager = mock_auth_manager.return_value

        result = automation.ensure_authentication()
        assert result is True
        assert automation.session is not None

    def test_batch_size_selection(self, automation):
        """Test automatic batch size selection."""
        # Small batch - should use sequential (≤5)
        small_credentials = [("user1", "pass1"), ("user2", "pass2")]
        assert automation._select_processing_method(small_credentials) == "sequential"

        # Medium batch - should use parallel (6-50)
        medium_credentials = [("user" + str(i), "pass" + str(i)) for i in range(10)]
        assert automation._select_processing_method(medium_credentials) == "parallel"

        # Large batch - should use optimized single script (>50)
        large_credentials = [("user" + str(i), "pass" + str(i)) for i in range(100)]
        assert automation._select_processing_method(large_credentials) == "optimized"

    def test_calculate_optimal_threads(self, automation):
        """Test optimal thread calculation."""
        # Small dataset
        threads = automation._calculate_optimal_threads(5)
        assert 1 <= threads <= 5

        # Large dataset
        threads = automation._calculate_optimal_threads(100)
        assert 5 <= threads <= 20

    def test_validate_jenkins_access_success(self, automation):
        """Test successful Jenkins access validation."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        automation.session = mock_session

        with patch.object(automation, 'ensure_authentication', return_value=True):
            result = automation.validate_jenkins_access()
            assert result is True

    def test_validate_jenkins_access_failure(self, automation):
        """Test failed Jenkins access validation."""
        with patch.object(automation, 'ensure_authentication', return_value=False):
            result = automation.validate_jenkins_access()
            assert result is False


class TestJenkinsAuthManagerSimple:
    """Simple test cases for JenkinsAuthManager."""

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
        # Should return None initially since no authentication has been done
        method = auth_manager.get_auth_method()
        assert method is None
