# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Linux Foundation project mapping and aliases."""

from typing import Dict, List, Optional, Tuple, TypedDict


class ProjectInfo(TypedDict):
    """Type definition for project information."""
    name: str
    full_name: str
    jenkins_url: Optional[str]
    aliases: List[str]
    has_jenkins: bool


# Project mappings with aliases and variations
PROJECT_MAPPINGS: Dict[str, ProjectInfo] = {
    "agl": {
        "name": "AGL",
        "full_name": "Automotive Grade Linux",
        "jenkins_url": "https://build.automotivelinux.org",
        "aliases": ["automotive-grade-linux", "automotivelinux"],
        "has_jenkins": True,
    },
    "akraino": {
        "name": "Akraino",
        "full_name": "Akraino Edge Stack",
        "jenkins_url": "https://jenkins.akraino.org",
        "aliases": ["akraino-edge-stack"],
        "has_jenkins": True,
    },
    "anuket": {
        "name": "Anuket",
        "full_name": "Anuket (Formerly OPNFV)",
        "jenkins_url": None,  # Uses GitLab CI
        "aliases": ["opnfv", "anuket-opnfv"],
        "has_jenkins": False,
    },
    "edgex": {
        "name": "EdgeX",
        "full_name": "EdgeX Foundry",
        "jenkins_url": "https://jenkins.edgexfoundry.org",
        "aliases": ["edgexfoundry", "edgex-foundry"],
        "has_jenkins": True,
    },
    "fdio": {
        "name": "FD.io",
        "full_name": "Fast Data Project",
        "jenkins_url": "https://jenkins.fd.io",
        "aliases": ["fast-data", "fdio"],
        "has_jenkins": True,
    },
    "hyperledger": {
        "name": "HyperLedger",
        "full_name": "Hyperledger",
        "jenkins_url": None,  # Uses GitHub Actions
        "aliases": ["hyperledger"],
        "has_jenkins": False,
    },
    "lf-broadband": {
        "name": "LF Broadband",
        "full_name": "Linux Foundation Broadband",
        "jenkins_url": "https://jenkins.opencord.org",
        "aliases": ["opencord", "voltha", "lf-broadband"],
        "has_jenkins": True,
    },
    "lf-edge": {
        "name": "LF Edge",
        "full_name": "Linux Foundation Edge",
        "jenkins_url": None,  # Uses GitHub Actions
        "aliases": ["lfedge", "lf-edge"],
        "has_jenkins": False,
    },
    "odpi": {
        "name": "ODPi",
        "full_name": "Open Data Platform Initiative",
        "jenkins_url": None,  # Uses Azure Pipelines
        "aliases": ["open-data-platform"],
        "has_jenkins": False,
    },
    "onap": {
        "name": "ONAP",
        "full_name": "Open Network Automation Platform",
        "jenkins_url": "https://jenkins.onap.org",
        "aliases": ["ecomp", "open-network-automation-platform"],
        "has_jenkins": True,
    },
    "opendaylight": {
        "name": "OpenDaylight",
        "full_name": "OpenDaylight Project",
        "jenkins_url": "https://jenkins.opendaylight.org/releng",
        "aliases": ["odl", "opendaylight-project"],
        "has_jenkins": True,
    },
    "o-ran-sc": {
        "name": "O-RAN",
        "full_name": "O-RAN Software Community",
        "jenkins_url": "https://jenkins.o-ran-sc.org",
        "aliases": ["oran", "o-ran", "oran-sc", "o-ran-software-community"],
        "has_jenkins": True,
    },
    "zowe": {
        "name": "Zowe",
        "full_name": "Zowe Open Mainframe Project",
        "jenkins_url": None,  # Uses GitHub Actions
        "aliases": ["open-mainframe", "openmainframe"],
        "has_jenkins": False,
    },
}

# Additional project information for fuzzy matching
PROJECT_DESCRIPTIONS: Dict[str, str] = {
    "agl": "Automotive Grade Linux (AGL) is an open source project that provides a framework for automotive infotainment systems.",
    "akraino": "Akraino Edge Stack is an open source software stack that supports high-availability cloud services optimized for edge computing systems.",
    "anuket": "Anuket (formerly OPNFV) develops and maintains a unified testing framework for Network Function Virtualization (NFV) infrastructure.",
    "edgex": "EdgeX Foundry is a vendor-neutral open source project building a common open framework for IoT edge computing.",
    "fdio": "FD.io (Fast Data Project) creates a high-performance packet processing library and framework for data plane applications.",
    "onap": "ONAP (Open Network Automation Platform) is a comprehensive platform for orchestrating and automating network services.",
    "opendaylight": "OpenDaylight (ODL) is an open-source application development and delivery platform for Software-Defined Networking (SDN).",
    "o-ran-sc": "O-RAN Software Community develops open source software for the O-RAN architecture supporting 5G and beyond networks.",
}


def get_projects_with_jenkins() -> List[Tuple[str, ProjectInfo]]:
    """Return list of projects that have Jenkins servers."""
    return [(key, project) for key, project in PROJECT_MAPPINGS.items() if project["has_jenkins"]]


def find_project_by_alias(search_term: str) -> Optional[str]:
    """Find a project key by searching through aliases and names."""
    search_term_lower = search_term.lower().replace("-", "").replace("_", "")
    
    for key, project in PROJECT_MAPPINGS.items():
        # Check exact key match
        if key.lower().replace("-", "").replace("_", "") == search_term_lower:
            return key
            
        # Check name match
        if project["name"].lower().replace("-", "").replace("_", "") == search_term_lower:
            return key
            
        # Check aliases
        for alias in project["aliases"]:
            if alias.lower().replace("-", "").replace("_", "") == search_term_lower:
                return key
    
    return None


def get_jenkins_projects() -> List[str]:
    """Get list of project keys that have Jenkins servers."""
    return [key for key, project in PROJECT_MAPPINGS.items() if project["has_jenkins"]]
