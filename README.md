<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Jenkins Credential Extractor

A CLI tool to bulk extract credentials from Jenkins servers in Linux Foundation projects.

## Features

- **Tailscale Integration**: Automatically discovers Jenkins servers in your Tailscale VPN network
- **Project Selection**: Interactive selection from Linux Foundation projects with fuzzy matching
- **Secure Downloads**: Uses SCP to download credentials.xml files respecting SSH configurations
- **Smart Server Filtering**: Automatically filters out sandbox servers and prefers production instances
- **Custom Pattern Matching**: Enter custom substrings to match credential descriptions (e.g., "Nexus deployment")
- **Automated Password Decryption**: Attempts to automatically decrypt passwords via Jenkins script console
- **Rich CLI**: Beautiful terminal interface with colored output and progress indicators

## Quick Start

```bash
# Install
git clone https://github.com/ModeSevenIndustrialSolutions/jenkins-credentials.git
cd jenkins-credentials
pip install -e .

# Extract credentials interactively
jenkins-credential-extractor extract
# or use the short alias
jce extract
```

## Installation

### Prerequisites

1. **Tailscale**: Must be installed and logged in
   - macOS: Tailscale app installed in `/Applications/`
   - Linux: `tailscale` command available in PATH

2. **SSH Access**: SSH key-based authentication to Jenkins servers

3. **Jenkins Access**: Access to Jenkins script console for password decryption

### From Source

```bash
git clone https://github.com/ModeSevenIndustrialSolutions/jenkins-credentials.git
cd jenkins-credentials
pip install -e .
```

## Usage

### Available Commands

```bash
# Interactive mode - select project from list
jce extract

# Specify project directly
jce extract o-ran-sc

# Custom output file
jce extract --output my-creds.txt

# Use custom pattern for credential matching
jce extract --pattern "Nexus deployment"

# Parse a local credentials.xml file
jce parse-local credentials.xml

# List available projects
jce list-projects

# Show Jenkins servers available in Tailscale network
jce list-servers
```

### Example Workflow

1. **Check Tailscale Status**
   ```bash
   jce list-servers
   ```

2. **Select Project and Extract**
   ```bash
   jce extract
   ```
   - Choose from available projects
   - Tool finds corresponding Jenkins server automatically

3. **Choose Credential Pattern**
   - **Option 0**: Enter custom substring (e.g., "Nexus deployment")
   - **Options 1-N**: Pre-defined patterns based on credential descriptions
   - **Last Option**: Extract all repository credentials

4. **Automated Decryption**
   - Tool attempts automated decryption via Jenkins script console
   - Falls back to manual process if automation fails

5. **Results**
   - Clean `credentials.txt` file with decrypted passwords

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

## Key Features

### Enhanced Server Filtering

Automatically filters and prioritizes Jenkins servers:
- **Removes** sandbox servers from listings
- **Prefers** production servers (containing 'prod')
- **Selects** lowest-numbered instances (jenkins-1 over jenkins-2)

### Custom Pattern Matching

New flexible credential selection:
```
Available credential description patterns:
  0. Enter a substring to match credentials
  1. Nexus Docker Read-Only
  2. aal Nexus deployment
  ...
  177. Extract all repository credentials

Select pattern (0-177): 0
Enter string: Nexus deployment
Found 159 credentials matching 'Nexus deployment'
```

### Automated Password Decryption

Attempts automation via Jenkins script console:
```groovy
encrypted_pw = '{AQAAABAAAAAw...}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
```

## Configuration

### SSH Configuration

The tool respects your existing SSH setup:
- SSH keys in `~/.ssh/`
- SSH config in `~/.ssh/config`
- SSH agent authentication
- Hardware security keys (YubiKey, etc.)

### Tailscale Setup

Ensure Tailscale is installed and authenticated:
```bash
tailscale status
```

## Output Format

Generated `credentials.txt` file format:
```
decrypted_password1 repository_name1
decrypted_password2 repository_name2
```

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

### Code Quality

```bash
# Run linting
ruff check .
ruff format .

# Type checking
mypy src/

# Run all pre-commit hooks
pre-commit run --all-files
```

### Running Tests

```bash
pytest
```

## Security Considerations

- **No Password Storage**: Tool never stores decrypted passwords except in final output
- **SSH Respect**: Uses your existing SSH configuration and keys
- **Manual Verification**: Password decryption can be verified manually if needed
- **Local Processing**: All credential parsing happens locally

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
- [ ] Support for additional credential types
- [ ] Bulk processing across multiple projects
- [ ] Integration with credential management systems
