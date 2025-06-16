# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Test credentials parser."""

import tempfile
from pathlib import Path

import pytest

from jenkins_credential_extractor.credentials import CredentialsParser


def test_credentials_parser_init() -> None:
    """Test credentials parser initialization."""
    parser = CredentialsParser("test.xml")
    assert parser.credentials_file == "test.xml"
    assert parser.root is None


def test_credentials_parser_file_not_found() -> None:
    """Test parser with non-existent file."""
    parser = CredentialsParser("nonexistent.xml")
    assert not parser.parse()


def test_credentials_parser_with_sample_file() -> None:
    """Test parser with sample credentials file."""
    # Use the sample file from resources
    sample_file = Path(__file__).parent.parent / "resources" / "credentials.xml"
    if not sample_file.exists():
        pytest.skip("Sample credentials.xml file not found")

    parser = CredentialsParser(str(sample_file))
    assert parser.parse()

    # Test extraction
    credentials = parser.extract_nexus_credentials()
    assert isinstance(credentials, list)

    # Should find some repository credentials
    assert len(credentials) > 0

    for username, encrypted_password in credentials:
        assert isinstance(username, str)
        assert isinstance(encrypted_password, str)
        assert len(encrypted_password) > 0


def test_credentials_parser_minimal_xml() -> None:
    """Test parser with minimal valid XML."""
    xml_content = """<?xml version='1.1' encoding='UTF-8'?>
<com.cloudbees.plugins.credentials.SystemCredentialsProvider>
  <domainCredentialsMap class="hudson.util.CopyOnWriteMap$Hash">
    <entry>
      <com.cloudbees.plugins.credentials.domains.Domain>
        <specifications/>
      </com.cloudbees.plugins.credentials.domains.Domain>
      <java.util.concurrent.CopyOnWriteArrayList>
        <com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
          <scope>GLOBAL</scope>
          <id>test-repo</id>
          <description>Test Repository</description>
          <username>test-user</username>
          <password>{AQAAABAAAAAwy5gL4M5KpiHQ9KdYUUv5QxXNpDT9vMA3gWHIQAaeWKlH}</password>
        </com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
      </java.util.concurrent.CopyOnWriteArrayList>
    </entry>
  </domainCredentialsMap>
</com.cloudbees.plugins.credentials.SystemCredentialsProvider>"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(xml_content)
        f.flush()

        parser = CredentialsParser(f.name)
        assert parser.parse()

        credentials = parser.extract_nexus_credentials()
        assert len(credentials) == 1

        username, encrypted_password = credentials[0]
        assert username == "test-user"
        assert encrypted_password == "AQAAABAAAAAwy5gL4M5KpiHQ9KdYUUv5QxXNpDT9vMA3gWHIQAaeWKlH"

    # Clean up
    Path(f.name).unlink()
