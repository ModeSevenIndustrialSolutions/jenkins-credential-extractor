# Jenkins Credential Extractor

A CLI tool to bulk extract credentials from Jenkins servers in Linux Foundation projects.

## Features

- **Tailscale Integration**: Automatically discovers Jenkins servers in your Tailscale VPN network
- **Project Selection**: Interactive selection from Linux Foundation projects with fuzzy matching
- **Secure Downloads**: Uses SCP to download credentials.xml files respecting SSH configurations
- **Password Decryption**: Guides you through decrypting Jenkins passwords via script console
- **Rich CLI**: Beautiful terminal interface with colored output and progress indicators

## Installation

### From Source

```bash
git clone https://github.com/ModeSevenIndustrialSolutions/jenkins-credentials.git
cd jenkins-credentials
pip install -e .
```

### From PyPI (coming soon)

```bash
pip install jenkins-credential-extractor
```

## Prerequisites

1. **Tailscale**: Must be installed and logged in
   - macOS: Tailscale app installed in `/Applications/`
   - Linux: `tailscale` command available in PATH

2. **SSH Access**: SSH key-based authentication to Jenkins servers

3. **Jenkins Access**: Access to Jenkins script console for password decryption

## Usage

### Quick Start

```bash
# Extract credentials interactively
jenkins-credential-extractor extract

# Or use the short alias
jce extract
```

### Available Commands

#### Extract Credentials
```bash
# Interactive mode - select project from list
jce extract

# Specify project directly
jce extract o-ran-sc

# Custom output file
jce extract --output my-creds.txt

# Custom credentials file location
jce extract --credentials-file /path/to/credentials.xml
```

#### List Projects
```bash
# Show all available projects with Jenkins servers
jce list-projects
```

#### List Jenkins Servers
```bash
# Show Jenkins servers available in Tailscale network
jce list-servers
```

#### Parse Local File
```bash
# Parse a local credentials.xml file without downloading
jce parse-local credentials.xml
```

### Example Workflow

1. **Check Tailscale Status**
   ```bash
   jce list-servers
   ```

2. **Select Project**
   ```bash
   jce extract
   ```
   - Choose from available projects
   - Tool finds corresponding Jenkins server automatically

3. **Download Credentials**
   - Tool uses SCP to download `/var/lib/jenkins/credentials.xml`
   - Respects your SSH configuration and authentication

4. **Decrypt Passwords**
   - For each credential, tool provides Jenkins script console commands
   - You copy/paste the decryption script and enter the results
   - Example script:
     ```groovy
     encrypted_pw = '{AQAAABAAAAAw...}'
     passwd = hudson.util.Secret.decrypt(encrypted_pw)
     println(passwd)
     ```

5. **Save Results**
   - Decrypted credentials saved to `credentials.txt`
   - Format: `password username`

## Supported Projects

The tool supports Linux Foundation projects with Jenkins servers:

- **AGL** (Automotive Grade Linux)
- **Akraino** (Edge Stack)
- **EdgeX** (Foundry)
- **FD.io** (Fast Data Project)
- **LF Broadband** (OpenCORD/VOLTHA)
- **ONAP** (Open Network Automation Platform)
- **OpenDaylight** (SDN Platform)
- **O-RAN-SC** (O-RAN Software Community)

### Project Aliases

The tool supports fuzzy matching and aliases:

- **OpenDaylight**: `odl`, `opendaylight`
- **ONAP**: `ecomp`, `onap`
- **O-RAN-SC**: `oran`, `o-ran`, `oran-sc`
- **Anuket**: `opnfv`, `anuket` (note: uses GitLab CI, not Jenkins)

## Configuration

### Tailscale Setup

**macOS:**
```bash
# Ensure Tailscale is installed and logged in
/Applications/Tailscale.app/Contents/MacOS/Tailscale status
```

**Linux:**
```bash
# Ensure Tailscale is installed and logged in
tailscale status
```

### SSH Configuration

Ensure you have SSH access to Jenkins servers. The tool respects:
- SSH keys in `~/.ssh/`
- SSH config in `~/.ssh/config`
- SSH agent authentication
- Hardware security keys (YubiKey, etc.)

## Output Format

The tool generates a `credentials.txt` file with format:
```
decrypted_password1 repository_name1
decrypted_password2 repository_name2
```

## Security Considerations

- **No Password Storage**: Tool never stores decrypted passwords except in the final output
- **SSH Respect**: Uses your existing SSH configuration and keys
- **Manual Decryption**: Requires manual interaction with Jenkins script console for security
- **Local Processing**: All credential parsing happens locally

## Development

### Setup Development Environment

```bash
git clone https://github.com/ModeSevenIndustrialSolutions/jenkins-credentials.git
cd jenkins-credentials

# Install with development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Run linting
ruff check .
ruff format .

# Type checking
mypy src/
```

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Ensure all tests and linting pass
6. Submit a pull request

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/ModeSevenIndustrialSolutions/jenkins-credentials/issues)
- Documentation: This README and inline help (`jce --help`)

## Roadmap

- [ ] PyPI package publication
- [ ] Automated password decryption (where security permits)
- [ ] Support for additional credential types
- [ ] Bulk processing across multiple projects
- [ ] Integration with credential management systems
