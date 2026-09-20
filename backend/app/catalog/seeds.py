from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import (
    CapabilityIn,
    ProductCapabilityIn,
    ProductEdgeIn,
    ProductIn,
    ReferenceArchitectureIn,
    ReferenceArchitectureProductItem,
)
from app.catalog.service import CatalogService
from app.db.models import (
    DeploymentModel,
    Document,
    DocumentChunk,
    DocumentStatus,
    EdgeStatus,
    LifecycleStatus,
    Ownership,
    Product,
    RelationType,
    SourceType,
    Workspace,
)

# ---------------------------------------------------------------------------
# 18 Controlled Capabilities
# ---------------------------------------------------------------------------

SEED_CAPABILITIES: list[dict[str, str]] = [
    {
        "name": "Identity Federation",
        "slug": "identity-federation",
        "category": "Identity & Access",
        "description": "SAML 2.0 and OIDC identity brokering across multi-tenant enterprise domains.",
    },
    {
        "name": "Single Sign-On (SSO)",
        "slug": "single-sign-on",
        "category": "Identity & Access",
        "description": "Centralized authentication and seamless web portal authorization.",
    },
    {
        "name": "Zero Trust Network Access (ZTNA)",
        "slug": "zero-trust-network-access",
        "category": "Cybersecurity",
        "description": "Least-privilege contextual application micro-tunnels without perimeter VPN exposure.",
    },
    {
        "name": "Next-Gen Firewall Inspection",
        "slug": "ngfw-inspection",
        "category": "Cybersecurity",
        "description": "Layer 7 application inspection, TLS decryption, and deep packet threat prevention.",
    },
    {
        "name": "Security Event Correlation (SIEM)",
        "slug": "siem-correlation",
        "category": "Cybersecurity",
        "description": "Centralized log analytics, anomaly detection, and automated threat hunting.",
    },
    {
        "name": "Hardware Security Module (HSM)",
        "slug": "hardware-security-module",
        "category": "Security & Compliance",
        "description": "FIPS 140-2 cryptographic key lifecycle management and envelope encryption.",
    },
    {
        "name": "Object Storage Service",
        "slug": "object-storage-service",
        "category": "Storage & Compute",
        "description": "S3-compatible immutable object store with lifecycle tiered storage.",
    },
    {
        "name": "Block Storage SAN",
        "slug": "block-storage-san",
        "category": "Storage & Compute",
        "description": "High-IOPS NVMe-over-Fabrics all-flash low-latency block storage.",
    },
    {
        "name": "Distributed Tracing & APM",
        "slug": "distributed-tracing-apm",
        "category": "Observability",
        "description": "OpenTelemetry-native distributed trace visualization and latency breakdown.",
    },
    {
        "name": "Infrastructure Metric Monitoring",
        "slug": "infrastructure-metric-monitoring",
        "category": "Observability",
        "description": "High-cardinality time-series metric collection, dashboards, and automated alerts.",
    },
    {
        "name": "Service Mesh mTLS",
        "slug": "service-mesh-mtls",
        "category": "Networking",
        "description": "Mutual TLS service-to-service encryption, canary routing, and circuit breaking.",
    },
    {
        "name": "Campus Network Switching",
        "slug": "campus-network-switching",
        "category": "Networking",
        "description": "High-density multi-gigabit access and core network switching fabric.",
    },
    {
        "name": "Direct Cloud Interconnect",
        "slug": "direct-cloud-interconnect",
        "category": "Cloud Connectivity",
        "description": "Dedicated private layer-2/layer-3 connectivity into public cloud VPCs.",
    },
    {
        "name": "API Schema Validation & Throttling",
        "slug": "api-schema-validation",
        "category": "API & Integration",
        "description": "API gateway request filtering, token introspection, and distributed rate limiting.",
    },
    {
        "name": "Multi-Tenant Container Runtime",
        "slug": "container-runtime",
        "category": "Compute & Containers",
        "description": "Hardened Kubernetes runtime environment with OCI container isolation.",
    },
    {
        "name": "Event Streaming Architecture",
        "slug": "event-streaming-architecture",
        "category": "Event Streaming",
        "description": "High-throughput fault-tolerant event broker compatible with Kafka protocols.",
    },
    {
        "name": "Data Warehousing & SQL Analytics",
        "slug": "data-warehousing-sql",
        "category": "Data & AI",
        "description": "Separation of storage and compute for petabyte-scale concurrent analytical SQL.",
    },
    {
        "name": "Cloud VoIP & Video Conferencing",
        "slug": "cloud-voip-video",
        "category": "Collaboration",
        "description": "SIP trunking, enterprise PBX routing, and encrypted HD video collaboration.",
    },
]

# ---------------------------------------------------------------------------
# 20 Curated Products (10 Own, 10 Resold)
# ---------------------------------------------------------------------------

SEED_PRODUCTS: list[dict[str, Any]] = [
    # 1. Own Product: Apex Identity Broker
    {
        "name": "Apex Identity Broker",
        "slug": "apex-identity-broker",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Identity & Access",
        "tier": "Core",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "DNS zone control and TLS certificates.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Central identity federation and authentication broker supporting SAML 2.0, OIDC, and multi-directory sync.",
        "capabilities": ["identity-federation", "single-sign-on"],
    },
    # 2. Own Product: Aegis Zero Trust Gateway
    {
        "name": "Aegis Zero Trust Gateway",
        "slug": "aegis-zero-trust-gateway",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Cybersecurity",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "seat-based",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Requires Apex Identity Broker or an approved IdP for token validation.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "ZTNA software-defined perimeter providing micro-segmented user-to-app tunnels without exposing private IP ranges.",
        "capabilities": ["zero-trust-network-access"],
    },
    # 3. Own Product: Nova Cloud Storage
    {
        "name": "Nova Cloud Storage",
        "slug": "nova-cloud-storage",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Storage & Compute",
        "tier": "Core",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "S3-compatible API client, IAM access credentials.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Distributed immutable object storage engine with continuous replication, versioning, and lifecycle expiration policies.",
        "capabilities": ["object-storage-service"],
    },
    # 4. Own Product: Strata Observability Platform
    {
        "name": "Strata Observability Platform",
        "slug": "strata-observability-platform",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Observability",
        "tier": "Core",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "OpenTelemetry agent instrumentation or Prometheus exporter endpoint.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "High-throughput log analytics, distributed tracing, and real-time metric visualization engine.",
        "capabilities": ["distributed-tracing-apm", "infrastructure-metric-monitoring"],
    },
    # 5. Own Product: Nexus Service Mesh
    {
        "name": "Nexus Service Mesh",
        "slug": "nexus-service-mesh",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Networking",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Requires Helios Container Engine or Kubernetes 1.28+ cluster.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Envoy-based microservices service mesh delivering automatic mTLS encryption, traffic shifting, and failure injection.",
        "capabilities": ["service-mesh-mtls"],
    },
    # 6. Own Product: Krypton Key Vault
    {
        "name": "Krypton Key Vault",
        "slug": "krypton-key-vault",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Security & Compliance",
        "tier": "Add-on",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Requires Apex Identity Broker for RBAC policy enforcement.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Hardware-backed cryptographic key management service with automated secret rotation and envelope encryption.",
        "capabilities": ["hardware-security-module"],
    },
    # 7. Own Product: Vanguard SIEM
    {
        "name": "Vanguard SIEM",
        "slug": "vanguard-siem",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Cybersecurity",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Syslog, CEF, or API webhook log forwarders.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Next-generation security information and event management platform with AI-driven correlation rules and automated playbook dispatch.",
        "capabilities": ["siem-correlation"],
    },
    # 8. Own Product: Prism API Gateway
    {
        "name": "Prism API Gateway",
        "slug": "prism-api-gateway",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "API & Integration",
        "tier": "Core",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Upstream backend HTTP/REST or gRPC services.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "High-performance edge API gateway providing JWT validation, rate limiting, and request transformation.",
        "capabilities": ["api-schema-validation"],
    },
    # 9. Own Product: Helios Container Engine
    {
        "name": "Helios Container Engine",
        "slug": "helios-container-engine",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Compute & Containers",
        "tier": "Core",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "perpetual",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Linux x86_64 or ARM64 bare-metal/virtual host with cgroups v2 enabled.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Hardened, multi-tenant container orchestration engine compliant with Kubernetes specifications and strict kernel isolation.",
        "capabilities": ["container-runtime"],
    },
    # 10. Own Product: Aether Messaging Bus
    {
        "name": "Aether Messaging Bus",
        "slug": "aether-messaging-bus",
        "vendor": "Apex Platform",
        "ownership": Ownership.OWN,
        "category": "Event Streaming",
        "tier": "Add-on",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "prerequisites": "Requires Helios Container Engine or cluster infrastructure.",
        "support_path": "Tier 1-3 24/7 dedicated engineering support.",
        "description": "Kafka-compatible distributed log streaming service built for sub-millisecond decoupled microservice events.",
        "capabilities": ["event-streaming-architecture"],
    },
    # 11. Resold: Okta Workforce Identity Cloud
    {
        "name": "Okta Workforce Identity Cloud",
        "slug": "okta-workforce-identity-cloud",
        "vendor": "Okta",
        "ownership": Ownership.RESOLD,
        "category": "Identity & Access",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "seat-based",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Premier Solution Provider",
        "margin_band": "18-22%",
        "support_owner": "vendor",
        "contract_constraints": "Collateral sharing subject to Okta Partner Agreement NDA; pricing confidential.",
        "source_of_truth_url": "https://www.okta.com/products/workforce-identity/",
        "prerequisites": "Corporate domain ownership and Active Directory / HRIS synchronization.",
        "support_path": "Direct Okta Platinum support with SE escalation bridge.",
        "description": "Industry-leading cloud identity, universal directory, and adaptive multi-factor authentication platform.",
        "capabilities": ["identity-federation", "single-sign-on"],
    },
    # 12. Resold: Microsoft Entra ID
    {
        "name": "Microsoft Entra ID",
        "slug": "microsoft-entra-id",
        "vendor": "Microsoft",
        "ownership": Ownership.RESOLD,
        "category": "Identity & Access",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "seat-based",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Gold Cloud Solutions Provider",
        "margin_band": "15-20%",
        "support_owner": "joint",
        "contract_constraints": "Standard Microsoft CSP commercial terms.",
        "source_of_truth_url": "https://www.microsoft.com/en-us/security/business/identity-access/microsoft-entra-id",
        "prerequisites": "Microsoft 365 or Azure subscription tenant.",
        "support_path": "Joint support: L1/L2 managed by SE team, L3 escalated to Microsoft Premier Support.",
        "description": "Cloud-based identity and access management solution for workforce and customer identities across hybrid ecosystems.",
        "capabilities": ["identity-federation", "single-sign-on"],
    },
    # 13. Resold: Palo Alto PA-Series Next-Gen Firewall
    {
        "name": "Palo Alto PA-Series Next-Gen Firewall",
        "slug": "palo-alto-pa-series-ngfw",
        "vendor": "Palo Alto Networks",
        "ownership": Ownership.RESOLD,
        "category": "Cybersecurity",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.ON_PREM,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Diamond Innovator Partner",
        "margin_band": "22-26%",
        "support_owner": "vendor",
        "contract_constraints": "Strict hardware export controls apply.",
        "source_of_truth_url": "https://www.paloaltonetworks.com/network-security/next-generation-firewalls",
        "prerequisites": "Rack space, redundant power, and dual 10G/40G SFP+ uplinks.",
        "support_path": "Palo Alto Networks Premium TAC with 4-hour hardware replacement.",
        "description": "Hardware and virtualized firewall appliances providing deep packet inspection, App-ID, and WildFire zero-day protection.",
        "capabilities": ["ngfw-inspection"],
    },
    # 14. Resold: Fortinet FortiGate UTM
    {
        "name": "Fortinet FortiGate UTM",
        "slug": "fortinet-fortigate-utm",
        "vendor": "Fortinet",
        "ownership": Ownership.RESOLD,
        "category": "Cybersecurity",
        "tier": "Standard",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "subscription",
        "target_segment": "Mid-Market",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Expert Solution Provider",
        "margin_band": "25-30%",
        "support_owner": "reseller",
        "contract_constraints": "Resale authorized in North America and EMEA territories.",
        "source_of_truth_url": "https://www.fortinet.com/products/next-generation-firewall",
        "prerequisites": "Standard datacenter or branch office networking topology.",
        "support_path": "Reseller-owned 24/7 technical hotline with Fortinet backline escalation.",
        "description": "Security-driven networking UTM appliance integrating firewall, SD-WAN, and antivirus inspection.",
        "capabilities": ["ngfw-inspection"],
    },
    # 15. Resold: Cisco Catalyst 9000 Switches
    {
        "name": "Cisco Catalyst 9000 Switches",
        "slug": "cisco-catalyst-9000",
        "vendor": "Cisco",
        "ownership": Ownership.RESOLD,
        "category": "Networking",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.ON_PREM,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Gold Certified Partner",
        "margin_band": "16-20%",
        "support_owner": "vendor",
        "contract_constraints": "Cisco DNA Premier license terms apply.",
        "source_of_truth_url": "https://www.cisco.com/c/en/us/products/switches/catalyst-9000.html",
        "prerequisites": "Structured cabling and PoE+ / UPOE power delivery.",
        "support_path": "Cisco Smart Net Total Care 24x7x4.",
        "description": "Enterprise campus access and core switching family supporting Cisco DNA software-defined access.",
        "capabilities": ["campus-network-switching"],
    },
    # 16. Resold: AWS Direct Connect
    {
        "name": "AWS Direct Connect",
        "slug": "aws-direct-connect",
        "vendor": "Amazon Web Services",
        "ownership": Ownership.RESOLD,
        "category": "Cloud Connectivity",
        "tier": "Core",
        "deployment_model": DeploymentModel.HYBRID,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "AWS Advanced Tier Partner",
        "margin_band": "8-12%",
        "support_owner": "vendor",
        "contract_constraints": "AWS Customer Agreement governs downstream accounts.",
        "source_of_truth_url": "https://aws.amazon.com/directconnect/",
        "prerequisites": "Colocation cross-connect or partner telecommunications circuit into AWS DX Point of Presence.",
        "support_path": "AWS Enterprise Support.",
        "description": "Dedicated private network connection linking on-premises infrastructure directly to AWS VPC resources.",
        "capabilities": ["direct-cloud-interconnect"],
    },
    # 17. Resold: Snowflake Data Cloud
    {
        "name": "Snowflake Data Cloud",
        "slug": "snowflake-data-cloud",
        "vendor": "Snowflake",
        "ownership": Ownership.RESOLD,
        "category": "Data & AI",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "consumption",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Elite Services Partner",
        "margin_band": "15-18%",
        "support_owner": "joint",
        "contract_constraints": "Usage-based commit contracts.",
        "source_of_truth_url": "https://www.snowflake.com/en/data-cloud/",
        "prerequisites": "Cloud object storage (Nova Cloud Storage, S3, or GCS) for staging data.",
        "support_path": "Joint support: Architecture and SQL optimization by internal SEs, infrastructure by Snowflake.",
        "description": "Fully managed multi-cloud data warehouse and analytics engine with decoupled compute and storage.",
        "capabilities": ["data-warehousing-sql"],
    },
    # 18. Resold: Datadog Cloud Monitoring
    {
        "name": "Datadog Cloud Monitoring",
        "slug": "datadog-cloud-monitoring",
        "vendor": "Datadog",
        "ownership": Ownership.RESOLD,
        "category": "Observability",
        "tier": "Core",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "subscription",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Gold Solution Partner",
        "margin_band": "18-22%",
        "support_owner": "vendor",
        "contract_constraints": "Host and custom metric ingestion quota constraints.",
        "source_of_truth_url": "https://www.datadoghq.com/",
        "prerequisites": "Datadog Agent installed across cluster nodes.",
        "support_path": "Datadog 24/7 Enterprise Support.",
        "description": "SaaS observability service providing end-to-end infrastructure monitoring, synthetics, and serverless telemetry.",
        "capabilities": ["infrastructure-metric-monitoring"],
    },
    # 19. Resold: Pure Storage FlashArray
    {
        "name": "Pure Storage FlashArray",
        "slug": "pure-storage-flasharray",
        "vendor": "Pure Storage",
        "ownership": Ownership.RESOLD,
        "category": "Storage & Compute",
        "tier": "Enterprise",
        "deployment_model": DeploymentModel.ON_PREM,
        "licensing_model": "perpetual",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Elite Reseller",
        "margin_band": "20-25%",
        "support_owner": "vendor",
        "contract_constraints": "Evergreen Storage maintenance agreement required.",
        "source_of_truth_url": "https://www.purestorage.com/products/flasharray.html",
        "prerequisites": "Fibre Channel or 25GbE iSCSI/NVMe-oF SAN infrastructure.",
        "support_path": "Pure Storage Pure1 24/7 proactive predictive support.",
        "description": "All-flash enterprise storage array delivering sub-millisecond block storage and deduplication.",
        "capabilities": ["block-storage-san"],
    },
    # 20. Resold: Zoom Phone & Meetings
    {
        "name": "Zoom Phone & Meetings",
        "slug": "zoom-phone-meetings",
        "vendor": "Zoom Video Communications",
        "ownership": Ownership.RESOLD,
        "category": "Collaboration",
        "tier": "Standard",
        "deployment_model": DeploymentModel.CLOUD,
        "licensing_model": "seat-based",
        "target_segment": "Enterprise",
        "lifecycle_status": LifecycleStatus.GA,
        "partner_tier": "Certified Partner",
        "margin_band": "20-25%",
        "support_owner": "joint",
        "contract_constraints": "E911 compliance and telecom carrier porting regulations apply.",
        "source_of_truth_url": "https://www.zoom.com/en/products/voip-phone/",
        "prerequisites": "Broadband internet connection and SIP-capable IP desk phones or Zoom client.",
        "support_path": "Joint support: L1 PBX routing handled by SEs, carrier escalation to Zoom.",
        "description": "Cloud phone system and enterprise video collaboration suite with global PSTN connectivity.",
        "capabilities": ["cloud-voip-video"],
    },
]

# ---------------------------------------------------------------------------
# Typed Relationships (25+ Edges)
# ---------------------------------------------------------------------------

SEED_EDGES: list[dict[str, Any]] = [
    # Prerequisites (requires)
    {
        "source": "aegis-zero-trust-gateway",
        "target": "apex-identity-broker",
        "relation_type": RelationType.REQUIRES,
        "evidence": "Aegis Zero Trust Gateway requires an OIDC/SAML token authority for device posture and identity validation before admitting micro-tunnels (Datasheet pg 4).",
        "confidence": 1.0,
    },
    {
        "source": "krypton-key-vault",
        "target": "apex-identity-broker",
        "relation_type": RelationType.REQUIRES,
        "evidence": "Krypton Key Vault requires Apex Identity Broker for cryptographic secret access control and RBAC authentication.",
        "confidence": 1.0,
    },
    {
        "source": "nexus-service-mesh",
        "target": "helios-container-engine",
        "relation_type": RelationType.REQUIRES,
        "evidence": "Nexus Service Mesh runs as an Envoy sidecar daemonset that strictly requires Helios Container Engine or a certified Kubernetes 1.28+ runtime.",
        "confidence": 1.0,
    },
    {
        "source": "aether-messaging-bus",
        "target": "helios-container-engine",
        "relation_type": RelationType.REQUIRES,
        "evidence": "Aether Messaging Bus nodes are distributed pods that require Helios Container Engine for cluster scheduling and persistent volume provisioning.",
        "confidence": 1.0,
    },
    # Cross-vendor Integrations (integrates_with)
    {
        "source": "apex-identity-broker",
        "target": "okta-workforce-identity-cloud",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Apex Identity Broker provides a certified inbound SAML/SCIM connector integrating seamlessly with Okta Workforce Identity Cloud.",
        "confidence": 0.95,
    },
    {
        "source": "apex-identity-broker",
        "target": "microsoft-entra-id",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Apex Identity Broker supports Azure AD / Microsoft Entra ID enterprise app federation via OpenID Connect and Graph API sync.",
        "confidence": 0.95,
    },
    {
        "source": "aegis-zero-trust-gateway",
        "target": "palo-alto-pa-series-ngfw",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Aegis Zero Trust Gateway can steer perimeter-bound untrusted traffic to Palo Alto PA-Series for deep packet threat inspection and WildFire sandboxing.",
        "confidence": 0.90,
    },
    {
        "source": "vanguard-siem",
        "target": "palo-alto-pa-series-ngfw",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Vanguard SIEM ingests real-time PAN-OS threat and traffic logs over TLS syslog to trigger automated firewall block rules.",
        "confidence": 0.95,
    },
    {
        "source": "vanguard-siem",
        "target": "fortinet-fortigate-utm",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Vanguard SIEM supports FortiOS native CEF log parser to correlate UTM antivirus, web filtering, and intrusion prevention events.",
        "confidence": 0.90,
    },
    {
        "source": "vanguard-siem",
        "target": "aegis-zero-trust-gateway",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Vanguard SIEM correlates ZTNA session metadata from Aegis Gateway to detect impossible travel and credential stuffing anomalies.",
        "confidence": 0.95,
    },
    {
        "source": "strata-observability-platform",
        "target": "datadog-cloud-monitoring",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Strata Observability Platform can stream summarized metrics and trace spans directly into Datadog via Datadog API Forwarder.",
        "confidence": 0.85,
    },
    {
        "source": "nova-cloud-storage",
        "target": "snowflake-data-cloud",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Nova Cloud Storage S3 endpoints act as an external stage for Snowflake Data Cloud continuous data loading (Snowpipe).",
        "confidence": 0.95,
    },
    {
        "source": "prism-api-gateway",
        "target": "nexus-service-mesh",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Prism API Gateway acts as an ingress gateway feeding routed traffic into the Nexus Service Mesh mTLS boundary.",
        "confidence": 0.95,
    },
    {
        "source": "cisco-catalyst-9000",
        "target": "aws-direct-connect",
        "relation_type": RelationType.INTEGRATES_WITH,
        "evidence": "Cisco Catalyst 9000 switches support 802.1Q VLAN trunking and BGP routing into AWS Direct Connect dedicated cloud circuits.",
        "confidence": 0.90,
    },
    # Bundles (bundles_with)
    {
        "source": "prism-api-gateway",
        "target": "aegis-zero-trust-gateway",
        "relation_type": RelationType.BUNDLES_WITH,
        "evidence": "Prism API Gateway and Aegis Zero Trust Gateway are frequently bundled to provide both edge API management and internal employee access control.",
        "confidence": 0.90,
    },
    {
        "source": "apex-identity-broker",
        "target": "aegis-zero-trust-gateway",
        "relation_type": RelationType.BUNDLES_WITH,
        "evidence": "Apex Identity Broker is bundled with Aegis Zero Trust Gateway as the standard Zero-Trust Starter Pack.",
        "confidence": 1.0,
    },
    # Alternatives (alternative_to)
    {
        "source": "nova-cloud-storage",
        "target": "pure-storage-flasharray",
        "relation_type": RelationType.ALTERNATIVE_TO,
        "evidence": "Nova Cloud Storage provides cloud-native S3 object persistence, serving as an alternative to on-premises SAN block storage like Pure Storage FlashArray for archival workloads.",
        "confidence": 0.85,
    },
    {
        "source": "datadog-cloud-monitoring",
        "target": "strata-observability-platform",
        "relation_type": RelationType.ALTERNATIVE_TO,
        "evidence": "Datadog Cloud Monitoring is a SaaS monitoring solution that functions as an alternative to self-hosted Strata Observability Platform.",
        "confidence": 0.90,
    },
    {
        "source": "fortinet-fortigate-utm",
        "target": "palo-alto-pa-series-ngfw",
        "relation_type": RelationType.ALTERNATIVE_TO,
        "evidence": "Fortinet FortiGate is a mid-market firewall alternative to the enterprise Palo Alto PA-Series.",
        "confidence": 0.95,
    },
    {
        "source": "microsoft-entra-id",
        "target": "okta-workforce-identity-cloud",
        "relation_type": RelationType.ALTERNATIVE_TO,
        "evidence": "Microsoft Entra ID and Okta Workforce Identity Cloud are direct enterprise alternatives in the identity and access management market.",
        "confidence": 0.95,
    },
    # Replacements (replaces)
    {
        "source": "aegis-zero-trust-gateway",
        "target": "fortinet-fortigate-utm",
        "relation_type": RelationType.REPLACES,
        "evidence": "Aegis Zero Trust Gateway replaces legacy client-to-site Fortinet SSL-VPN endpoints with modern identity-aware micro-tunnels.",
        "confidence": 0.85,
    },
    # Conflicts (conflicts_with)
    {
        "source": "aegis-zero-trust-gateway",
        "target": "pure-storage-flasharray",
        "relation_type": RelationType.CONFLICTS_WITH,
        "evidence": "Aegis Zero Trust Gateway operates at L7 user application layers and conflicts directly when forced over raw low-latency Fibre Channel block arrays.",
        "confidence": 0.90,
    },
]

# ---------------------------------------------------------------------------
# 3 Reference Architectures
# ---------------------------------------------------------------------------

SEED_ARCHITECTURES: list[dict[str, Any]] = [
    {
        "name": "Secure Hybrid Cloud Foundation",
        "slug": "secure-hybrid-cloud-foundation",
        "description": "Production blueprint connecting on-premises data centers to AWS cloud infrastructure with centralized identity and immutable storage.",
        "architecture_overview": (
            "### Architecture Flow\n"
            "1. **Identity Layer**: Apex Identity Broker federates enterprise directory credentials.\n"
            "2. **Zero-Trust Access**: Aegis Zero Trust Gateway provides remote SE and developer tunnels.\n"
            "3. **Connectivity**: AWS Direct Connect provides low-latency dedicated transport.\n"
            "4. **Storage Tier**: Nova Cloud Storage acts as the primary data lake repository."
        ),
        "target_segment": "Enterprise",
        "products": [
            {"slug": "apex-identity-broker", "role": "Core Identity Provider"},
            {"slug": "aegis-zero-trust-gateway", "role": "Zero Trust Perimeter"},
            {"slug": "aws-direct-connect", "role": "Private Hybrid Transport"},
            {"slug": "nova-cloud-storage", "role": "Object Storage Repository"},
        ],
    },
    {
        "name": "Enterprise Zero-Trust SOC",
        "slug": "enterprise-zero-trust-soc",
        "description": "Unified threat detection, perimeter defense, and secrets management for security operations teams.",
        "architecture_overview": (
            "### Architecture Flow\n"
            "1. **Detection**: Vanguard SIEM correlates event streams across firewalls and endpoints.\n"
            "2. **Perimeter Defense**: Palo Alto PA-Series enforces L7 traffic policies and deep packet inspection.\n"
            "3. **Telemetry**: Strata Observability Platform captures distributed runtime logs and traces.\n"
            "4. **Key Management**: Krypton Key Vault safeguards encryption keys for compliance."
        ),
        "target_segment": "Enterprise",
        "products": [
            {"slug": "vanguard-siem", "role": "SIEM Analytics Engine"},
            {"slug": "palo-alto-pa-series-ngfw", "role": "Perimeter Inspection"},
            {"slug": "strata-observability-platform", "role": "Telemetry Pipeline"},
            {"slug": "krypton-key-vault", "role": "HSM Key Store"},
        ],
    },
    {
        "name": "Microservices Production Edge",
        "slug": "microservices-production-edge",
        "description": "Cloud-native application runtime combining ingress routing, service mesh security, container orchestration, and metrics.",
        "architecture_overview": (
            "### Architecture Flow\n"
            "1. **Ingress & Rate Limiting**: Prism API Gateway filters external consumer traffic.\n"
            "2. **Service Mesh**: Nexus Service Mesh enforces mTLS and canary deployments.\n"
            "3. **Container Runtime**: Helios Container Engine executes microservice pods.\n"
            "4. **Monitoring**: Strata Observability Platform provides live latency traces."
        ),
        "target_segment": "Enterprise",
        "products": [
            {"slug": "prism-api-gateway", "role": "Edge API Gateway"},
            {"slug": "nexus-service-mesh", "role": "Service Mesh mTLS"},
            {"slug": "helios-container-engine", "role": "Kubernetes Runtime"},
            {"slug": "strata-observability-platform", "role": "Distributed APM"},
        ],
    },
]


def seed_phase4_catalog(
    db: Session,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> dict[str, int]:
    """Populates the database with the Phase 4 seed catalog.

    Exit Criterion:
    - All 20 products modeled with capabilities and edges.
    - Every product has at least one capability, one document, and one edge.
    - Zero cycles on requires edges.
    - Zero bundle contradictions.
    """
    service = CatalogService(db)

    # 1. Seed Capabilities
    capabilities_by_slug: dict[str, Any] = {}
    for cap_data in SEED_CAPABILITIES:
        cap = service.create_capability(
            org_id,
            CapabilityIn(
                name=cap_data["name"],
                slug=cap_data["slug"],
                category=cap_data["category"],
                description=cap_data["description"],
            ),
        )
        capabilities_by_slug[cap.slug] = cap

    # 2. Seed Synthetic Collateral Documents (to satisfy "every product has a document")
    products_by_slug: dict[str, Product] = {}
    for prod_data in SEED_PRODUCTS:
        # Check or create synthetic collateral document
        doc_filename = f"{prod_data['slug']}-datasheet.pdf"
        existing_doc = db.scalar(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.original_filename == doc_filename,
                Document.is_current.is_(True),
            )
        )
        if not existing_doc:
            existing_doc = Document(
                org_id=org_id,
                workspace_id=workspace_id,
                filename=doc_filename,
                original_filename=doc_filename,
                file_type="pdf",
                mime_type="application/pdf",
                storage_key=f"collateral/{workspace_id}/{doc_filename}",
                file_size=10240,
                title=f"{prod_data['name']} Official Technical Datasheet",
                vendor=prod_data["vendor"],
                ownership=prod_data["ownership"],
                products_referenced=[prod_data["name"], prod_data["slug"]],
                source_type=SourceType.UPLOAD,
                status=DocumentStatus.READY,
                chunk_count=1,
            )
            db.add(existing_doc)
            db.flush()

            # Add chunk for document
            chunk = DocumentChunk(
                document_id=existing_doc.id,
                org_id=org_id,
                chunk_index=0,
                page_number=1,
                text=(
                    f"Product Technical Overview: {prod_data['name']} by {prod_data['vendor']}. "
                    f"Category: {prod_data['category']}. Deployment: {prod_data['deployment_model']}. "
                    f"{prod_data['description']} Prerequisites: {prod_data['prerequisites']}."
                ),
            )
            db.add(chunk)
            db.flush()

        # Create Product
        prod_in = ProductIn(
            name=prod_data["name"],
            slug=prod_data["slug"],
            vendor=prod_data["vendor"],
            ownership=prod_data["ownership"],
            category=prod_data["category"],
            tier=prod_data["tier"],
            deployment_model=prod_data["deployment_model"],
            licensing_model=prod_data["licensing_model"],
            target_segment=prod_data["target_segment"],
            lifecycle_status=prod_data["lifecycle_status"],
            prerequisites=prod_data.get("prerequisites"),
            support_path=prod_data.get("support_path"),
            description=prod_data.get("description"),
            collateral_document_ids=[existing_doc.id],
            partner_tier=prod_data.get("partner_tier"),
            margin_band=prod_data.get("margin_band"),
            support_owner=prod_data.get("support_owner"),
            contract_constraints=prod_data.get("contract_constraints"),
            source_of_truth_url=prod_data.get("source_of_truth_url"),
        )
        product = service.create_product(org_id, workspace_id, prod_in)
        products_by_slug[product.slug] = product

        # Assign capabilities
        for cap_slug in prod_data.get("capabilities", []):
            if cap_slug in capabilities_by_slug:
                service.assign_capability_to_product(
                    product.id,
                    workspace_id,
                    ProductCapabilityIn(
                        capability_id=capabilities_by_slug[cap_slug].id,
                        proficiency="native",
                        notes=f"Native {capabilities_by_slug[cap_slug].name} feature",
                    ),
                )

    # 3. Seed Edges
    edges_created = 0
    for edge_data in SEED_EDGES:
        src = products_by_slug.get(edge_data["source"])
        tgt = products_by_slug.get(edge_data["target"])
        if src and tgt:
            service.create_edge(
                org_id,
                workspace_id,
                ProductEdgeIn(
                    source_product_id=src.id,
                    target_product_id=tgt.id,
                    relation_type=edge_data["relation_type"],
                    evidence=edge_data["evidence"],
                    confidence=edge_data["confidence"],
                    status=EdgeStatus.APPROVED,
                ),
            )
            edges_created += 1

    # 4. Seed Reference Architectures
    archs_created = 0
    for arch_data in SEED_ARCHITECTURES:
        arch_products: list[ReferenceArchitectureProductItem] = []
        for p_item in arch_data["products"]:
            p = products_by_slug.get(p_item["slug"])
            if p:
                arch_products.append(
                    ReferenceArchitectureProductItem(
                        product_id=p.id,
                        role=p_item["role"],
                    )
                )

        service.create_reference_architecture(
            org_id,
            workspace_id,
            ReferenceArchitectureIn(
                name=arch_data["name"],
                slug=arch_data["slug"],
                description=arch_data["description"],
                architecture_overview=arch_data["architecture_overview"],
                target_segment=arch_data["target_segment"],
                products=arch_products,
            ),
        )
        archs_created += 1

    return {
        "capabilities": len(capabilities_by_slug),
        "products": len(products_by_slug),
        "edges": edges_created,
        "architectures": archs_created,
    }
