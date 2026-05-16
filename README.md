# Structranet AI

**Natural Language → AI Designs Network → Validates → Exports Portable `.gns3project`**

Structranet AI is an AI-powered virtual network engineer that transforms natural language descriptions into fully configured, offline GNS3 network topologies. Describe the network you want in plain English, and Structranet AI designs the topology, assigns hardware, generates IP addressing and routing configurations, and exports it as a portable `.gns3project` ZIP file that can be imported directly into GNS3.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Pipeline](#pipeline)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Supported Device Types](#supported-device-types)
- [Key Design Decisions](#key-design-decisions)
- [Validation & Testing](#validation--testing)
- [Export Format](#export-format)
- [Configuration Reference](#configuration-reference)
- [Known Issues & Roadmap](#known-issues--roadmap)

---

## Overview

Network engineering is repetitive: spin up routers, assign IPs, configure routing protocols, wire switches. Structranet AI automates this entire workflow. A user describes their intent — *"Build a campus network with 3 VLANs, a core router, and 6 PCs"* — and the system:

1. Uses an LLM to design the logical topology (which devices, which connections)
2. Deterministically assigns adapter/port numbers (no LLM guesswork)
3. Injects the correct hardware expansion modules (slot modules, adapter counts)
4. Generates full software configurations (IPs, routing, VLANs, startup scripts)
5. Exports a portable `.gns3project` ZIP that can be imported into any GNS3 installation

Every constant, path format, and schema field has been validated against the **GNS3 2.2 server source code** to ensure the exported project files import cleanly without errors.

---

## Architecture

Structranet AI uses a **two-phase pipeline** that separates logical design from physical configuration:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: Topology + Hardware                                      │
│                                                                     │
│  User Input ──► AI Agent (LLM) ──► TopologyRequest                │
│       │              │                   (nodes + connections)      │
│       │              │                        │                     │
│       │              └─── Port Assigner ◄─────┘                    │
│       │                    (deterministic)                          │
│       │                        │                                    │
│       │                  GNS3Project                                │
│       │                        │                                    │
│       │              Hardware Injector                              │
│       │           (slots, adapters, ports_mapping)                  │
│       │                        │                                    │
│       │              Switch Port Patcher                            │
│       │           (VLAN trunk/access assignments)                   │
│       └────────────────────────│────────────────────────────────────┘
                                    │
┌───────────────────────────────────│─────────────────────────────────┐
│  Phase 2: Software Configuration  │                                 │
│                                   ▼                                 │
│  Context Builder ──► Config Brief ──► AI Agent (LLM)              │
│       │                                         │                   │
│       │                                  Software Configs           │
│       │                                   (IPs, routing, VLANs)     │
│       │                                         │                   │
│       └──────── Three-Gate Safe Merge ◄─────────┘                  │
│                  (whitelist → no-overwrite → type check)            │
│                        │                                            │
│                  Final Topology JSON                                │
└────────────────────────│────────────────────────────────────────────┘
                         │
                         ▼
              .gns3project ZIP Export
              (GNS3 object graph +
            config file extraction)
           (portable offline project)
```

---

## Pipeline

The full CLI pipeline now runs in 6 steps:

| Step | Module | Description |
|------|--------|-------------|
| 1/6 | Load catalog | Load built-in + custom appliance definitions |
| 2/6 | User input + Preflight | CLI argument or interactive prompt; collect environment profile (GNS3 version + supported node families + security profile) |
| 3/6 | `ai_agent` | LLM generates `TopologyRequest` (nodes + logical connections), constrained by profile support; security rules injected if profile != "none" |
| 4/6 | `port_assigner` → `hw_config` → `topology_finalizer` | Deterministic port assignment + hardware slot injection + VLAN switch-port patching |
| 5/6 | `config_agent` | LLM generates software configs (IPs, routing, startup scripts); security hardening applied if profile != "none" |
| 6/6 | `gns3_exporter` → `gns3project_validator` | Convert final topology JSON to portable `.gns3project` ZIP; run 11 structural checks to ensure import safety |

Before phase 2 and before final export, `main.py` presents review checkpoints so the user can approve or stop.

---

## Project Structure

```
structranet-ai/
├── main.py                     # Grand orchestrator — 6-step CLI pipeline
│
├── preflight.py                # Environment profile collection + compatibility gate + security profile
│
├── ai_agent.py                 # Phase 1: LLM topology generation (with optional security rules injection)
├── config_agent.py             # Phase 2: LLM software config generation (with optional security hardening)
├── security_prompts.py         # Security profile prompt injection (none/basic/enterprise)
├── schema.py                   # Pydantic models (TopologyRequest, GNS3Project, etc.)
│
├── port_assigner.py            # Deterministic adapter/port number assignment
├── hw_config.py                # Hardware injection (slots, adapters, ports_mapping)
├── topology_finalizer.py       # VLAN switch port patching (trunk/access)
├── context_builder.py          # Configuration brief builder + port name resolution
├── llm_utils.py                # Shared LLM utilities (client, retry logic, JSON extraction)
│
├── constants/                  # Shared constants package (single source of truth)
│   ├── gns3.py                 # GNS3 format constants
│   ├── hardware.py             # Hardware and node-type constants (SSOT)
│   ├── appliances.py           # Built-in appliance catalog constants
│   ├── phase2.py               # Phase 2 safe-merge constants
│   ├── ai.py                   # AI pipeline constants (retry/limits)
│   ├── validation.py           # Validation constants (backward-compat re-exports)
│   └── __init__.py             # Constants package init
├── appliance_catalog.py        # Static appliance definitions (Cisco 7200, IOU, VPCS, etc.)
│
├── gns3_exporter.py            # .gns3project ZIP archive packaging + verification
│
├── gns3project_validator.py    # Deep structural validator for .gns3project files
│
├── tests/
│   ├── test_golden_export.py   # Golden export + validator regression test
│   └── fixtures/
│       └── golden_minimal_topology.json
│
├── requirements.txt            # Python dependencies
└── output/                     # Generated topology files
    ├── _topology.json          # Phase 1 output (hardware-injected)
    ├── final_topology.json     # Phase 2 output (software configs merged)
    ├── preflight_profile.json  # Saved environment profile
    ├── generation_report.json  # Structured per-run report
    └── configs_review/         # Optional raw config export for pre-GNS3 review
```

### Module Responsibilities

| Module | Role | Key Functions |
|--------|------|---------------|
| `main.py` | Entry point & pipeline orchestration | `parse_args()`, `catalog_to_inventory()`, `main()` |
| `preflight.py` | Environment readiness checks + security profile | `collect_profile_interactive()`, `check_topology_compatibility()`, `filter_inventory_by_profile()` |
| `ai_agent.py` | LLM topology design (with security injection) | `generate_network_topology()`, `process_and_save_topology()`, `_build_step1_prompt()` (now accepts security_profile) |
| `config_agent.py` | LLM config generation (with security hardening) | `run_phase2()`, `safe_merge_configs()`, `generate_software_configs()` (now accepts security_profile) |
| `security_prompts.py` | Security profile prompt templates | `get_topology_security_prompt()`, `get_config_security_prompt()` |
| `schema.py` | Data contracts | `TopologyRequest`, `GNS3Project`, `validate_topology()`, `validate_topology_request()` |
| `port_assigner.py` | Port number math | `assign_ports()`, `build_topology_from_request()` |
| `hw_config.py` | Hardware expansion | `inject_hardware_config()` — Dynamips slots, IOU adapters, QEMU adapters, switch ports_mapping |
| `topology_finalizer.py` | VLAN switching | `apply_switch_port_patches()` — trunk/access/dot1q port rewrites |
| `context_builder.py` | LLM context builder | `build_configuration_brief()`, `resolve_port_name()`, `build_segments()` |
| `llm_utils.py` | Shared LLM utilities (SSOT) | `_get_client()`, `_call_with_retry()`, `_extract_json()` |
| `constants/gns3.py` | Shared GNS3 constants | `GNS3_REVISION`, `FILE_CONFIG_TRIPLETS`, `SYMBOL`, `PORT_NAME_FORMAT`, etc. |
| `constants/hardware.py` | Shared hardware constants (SSOT) | Dynamips module tables, adapter limits, node type sets, compatibility matrix |
| `constants/phase2.py` | Phase 2 merge constants | `SOFTWARE_CONFIG_KEYS`, `ALLOWED_VALUE_TYPES` |
| `constants/ai.py` | AI generation constants | `MAX_RETRIES`, prompt-side link-limit tables |
| `constants/appliances.py` | Appliance defaults constants | `APPLIANCE_CATALOG` |
| `constants/validation.py` | Validation re-exports | Backward-compatible re-exports from hardware.py & gns3.py |
| `appliance_catalog.py` | Template defaults loader | `get_appliance()`, `load_catalog()` with user overlay support |
| `gns3_exporter.py` | ZIP packaging | `convert()` |
| `gns3project_validator.py` | Deep validation | `GNS3ProjectValidator` — 11 structural checks against GNS3 spec |

---

## Getting Started

### Prerequisites

- Python 3.10+
- GNS3 2.2+ (for importing the exported project)
- An OpenAI-compatible LLM API key

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/structranet-ai.git
cd structranet-ai

# Install dependencies
pip install openai pydantic streamlit python-dotenv graphviz

# Create .env file
cat > .env << 'EOF'
ROUTER_API_KEY=your-api-key-here
ROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openrouter/owl-alpha
AI_MAX_TOKENS=8192
EOF
```

### Quick Start

**CLI mode:**
```bash
# Generate, export, and validate .gns3project
python main.py --request "Build a campus network with 2 routers, a core switch, 3 access switches, and 9 PCs across 3 VLANs"

# With security hardening (basic: SSH, AAA, NTP, Syslog)
python main.py --request "3-router topology" --security-profile basic

# Enterprise security (ZBF, ACLs, DAI, DHCP Snooping, SNMPv3, redundancy, HSRP)
python main.py --request "enterprise network" --security-profile enterprise

# Skip Phase 2 (software configs)
python main.py --request "3-router topology" --no-phase2

# Custom .gns3project output path
python main.py --request "3-router topology" --project-output output/my_lab.gns3project

# Skip validator (not recommended)
python main.py --request "3-router topology" --no-validate

# Export raw configs for pre-GNS3 review
python main.py --request "3-router topology" --configs ./config_review

# Use a saved preflight profile (non-interactive environment info)
python main.py --request "3-router topology" --profile output/preflight_profile.json

# Auto-approve interactive checkpoints
python main.py --request "3-router topology" --yes
```

**Programmatic export:**
```python
from gns3_exporter import convert

# Load the final topology
import json
with open("output/final_topology.json") as f:
    topology = json.load(f)

# Export as .gns3project ZIP
path = convert(topology, "my_network.gns3project")
print(f"Exported to: {path}")
# Import: GNS3 GUI → File → Import portable project
```

---

## Security Profiles

Structranet AI includes **three built-in security profiles** that automatically harden topologies and configurations. Profiles are selected during preflight or via the `--security-profile` CLI flag.

### Profile: "none" (Default)

- No security rules injected
- Pure lab/universal mode
- LLM designs topology without architectural constraints
- Configs contain only IP addressing and basic routing
- **Use case**: Educational labs, proof-of-concept builds, testing

### Profile: "basic"

Applies lightweight security hardening to every router:

**Topology rules**:
- Mandatory NAT node for Internet edge (`NAT-ISP`)
- Dedicated management VPCS host (`MGMT-PC` or `Admin-PC`)
- All hosts connect via switch (never directly to router)
- Node security fields: `security_role`, `zone` (OUTSIDE/INSIDE/MANAGEMENT)

**Config rules** (every router gets):
- SSH (v2) with 12-char min password requirement
- AAA (local authentication) with login rate-limiting
- Syslog/NTP with standard servers (10.0.10.50, 10.0.10.100)
- Service hardening (no finger, no small servers, source-route disable)
- Banner and session timeout enforcement

**Use case**: Small to medium labs with basic access controls

### Profile: "enterprise"

Full security archetype with Zone-Based Firewall (ZBF), redundancy, and defense-in-depth:

**Mandatory topology rules**:
- **Perimeter Router** (node_id: "FW" or "R-EDGE"): Zone-Based Firewall, connects to NAT/Internet
- **Core Switch** (node_id: "Core-SW"): Central distribution, VLAN aggregation
- **DMZ Switch** (node_id: "DMZ-SW"): Isolated for servers, connected to perimeter router
- **Management Switch** (node_id: "MGMT-SW"): Out-of-band management VLAN only
- **SIEM** (node_id: "SIEM"): Syslog/monitoring host on MGMT-SW
- **Secondary Router** (node_id: "FW2" or "R-EDGE2"): For ≥6-node topologies (redundancy via HSRP)

**VLAN segmentation** (auto-detected from switch names):
- VLAN 10 MGMT (`Mgmt`/`MGMT` prefix)
- VLAN 20 USERS (`User`/`LAN` prefix)
- VLAN 30 SERVERS (`Srv`/`Server` prefix)
- VLAN 40 VOIP (`VoIP`/`Voice` prefix)
- VLAN 50 IOT (`IoT` prefix)
- VLAN 60 DMZ (`DMZ` prefix)
- VLAN 100 GUEST (`Guest` prefix)
- VLAN 999 NATIVE-UNUSED (trunk native, prevents VLAN hopping)

**Config hardening** (every router gets):
- Full Block A (universal): SSH, AAA, NTP auth, SNMPv3, Syslog to SIEM, loopback0, domain-name
- Block B (perimeter router): **Zone-Based Firewall** (OUTSIDE/INSIDE/DMZ zones), anti-spoofing ACLs, TCP intercept (SYN flood protection), OSPF MD5 auth, NAT PAT overload
- Block C (secondary/internal): OSPF auth, HSRP with MD5 authentication, redundant link failover
- Block D (core/distribution switch): STP hardening, spanning-tree guard-root
- Block E (access switches): DHCP Snooping, DAI (Dynamic ARP Inspection), port-security, storm-control, BPDU Guard
- Block F (VPCS hosts): Auto-assigned IPs from VLAN subnets, correct gateway routing
- Block G (SIEM): Fixed IP on MGMT VLAN

**Use case**: Production networks, compliance-driven labs (PCI, HIPAA, enterprise security standards), realistic security training

---

### Preflight Profile JSON with Security

When using a saved preflight profile, include the `security_profile` field:

```json
{
  "gns3_version": "2.2.54",
  "supports_iou": false,
  "supports_qemu": true,
  "supports_docker": false,
  "strict_validation": true,
  "require_template_image_map": false,
  "template_image_map": {},
  "security_profile": "enterprise"
}
```

### CLI Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--request` | `-r` | Network description (skips interactive prompt) |
| `--output` | `-o` | Output JSON file path |
| `--catalog` | | Path to custom appliance catalog JSON overlay |
| `--profile` | | Path to preflight environment profile JSON |
| `--security-profile` | | Apply security hardening: `none` \| `basic` \| `enterprise` |
| `--no-phase2` | | Skip Phase 2 (software configuration generation) |
| `--project-output` | | Output `.gns3project` path |
| `--no-validate` | | Skip post-export structural validation |
| `--configs` | | Export raw configs to directory for pre-GNS3 review |
| `--yes` | | Auto-approve interactive checkpoints |

### Preflight Profile JSON

The profile file allows non-interactive, backend/frontend-friendly runs:

```json
{
  "gns3_version": "2.2.54",
  "supports_iou": false,
  "supports_qemu": true,
  "supports_docker": false,
  "strict_validation": true,
  "require_template_image_map": false,
  "template_image_map": {
    "Cisco 3745": "c3745-adventerprisek9-mz.124-25d.image",
    "Cisco 7200": "c7200-adventerprisek9-mz.124-24.T5.image"
  },
  "security_profile": "none"
}
```

- When `require_template_image_map=true`, appliance nodes must use template names present in `template_image_map`.
- During export, this map is passed to `gns3_exporter.convert(..., image_map=...)` to keep image selection deterministic.
- `security_profile` can be `"none"`, `"basic"`, or `"enterprise"` (see Security Profiles section above)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROUTER_API_KEY` | *(required)* | OpenAI-compatible API key |
| `ROUTER_BASE_URL` | *(required)* | LLM API base URL |
| `AI_MODEL` | `openrouter/owl-alpha` | LLM model identifier |
| `AI_MAX_TOKENS` | `8192` | Max tokens per LLM call |
| `STRUCTRANET_OUTPUT_DIR` | `output` | Output directory for topology files |

---

## Supported Device Types

Structranet AI supports all GNS3 node types with hardware-aware expansion:

### Routers (L3)

| Type | Platforms | Expansion | Built-in Ports |
|------|-----------|-----------|----------------|
| **Dynamips** | c7200, c3745, c3725, c3660, c3640, c3620, c2691, c2600, c1700 | Slot-based modules (PA-8E, NM-4E, PA-4T+, NM-4T, etc.) | 0-2 per platform |
| **IOU** | IOU L3, IOU L2 | Count-based (`ethernet_adapters`, `serial_adapters`, 4 ports each) | — |
| **QEMU** | CSR1000v, etc. | `adapters` integer (max 275) | — |
| **Docker** | Custom containers | `adapters` integer (max 99) | — |

### Switches & Hubs (L2)

| Type | Expansion | Port Format |
|------|-----------|-------------|
| **Ethernet Switch** | `ports_mapping` array (VLAN-aware: access/dot1q) | `Ethernet{N}` |
| **Ethernet Hub** | `ports_mapping` array | `Ethernet{N}` |

### End Devices

| Type | Ports | Config |
|------|-------|--------|
| **VPCS** | 1 (fixed) | `startup_script` |
| **TraceNG** | 1 (fixed) | — |
| **NAT** | 1 (fixed) | — |
| **Cloud** | Variable | — |

---

## Key Design Decisions

### 1. LLM Only Designs, Code Assigns Ports

The single largest source of deployment failures in previous versions was the LLM computing adapter/port numbers incorrectly. The current architecture strictly separates concerns:

- **LLM**: Decides *what* connects to *what* (logical topology)
- **Code**: Computes *where* on each device (adapter/port numbers) via `port_assigner.py`

This eliminates an entire class of bugs and reduces the LLM prompt from ~250 lines to ~80 lines.

### 2. Three-Gate Safe Merge

Phase 2 (software config generation) merges LLM output into the topology with three safety gates:

1. **Whitelist Gate**: Only `startup_config_content`, `startup_script`, `start_command`, and `environment` keys are allowed
2. **No-Overwrite Gate**: Hardware properties (slots, adapters, ports_mapping) can never be overwritten
3. **Type Gate**: Value types must match the expected type (string, dict, etc.)

This makes it **impossible** for the LLM to corrupt hardware configuration, regardless of what it generates.

### 3. Deterministic Output

The same topology JSON always produces the same `.gns3project` file:

- UUIDs are derived via UUID5 from (project_name, node_id) — not random
- Canvas coordinates are computed from device role priority and sorted node IDs
- Port assignments follow deterministic rules based on node type and link order

### 4. Single Source of Truth for Constants

The `constants/` package is the authoritative reference for shared constants:

- File format version/revision
- Config file path mappings (software_key x node_type → filesystem path)
- Visual defaults (symbols, console types, label styles)
- Port name format per node type
- Node type classifications (appliance, built-in, single-port, no-config)
- Layout grid constants

All values are verified against the GNS3 2.2 server source code.

### 5. Offline-First Export

The project pivoted from live GNS3 REST API deployment to offline `.gns3project` ZIP export. This means:

- No running GNS3 server is required to generate topologies
- Exported projects are fully portable and self-contained
- The same topology can be shared, version-controlled, and imported on any GNS3 installation
- Config files are embedded in the ZIP with correct GNS3 portable project paths

### 6. Validated Against GNS3 Source Code

Every constant in `constants/gns3.py`, every Dynamips module in `constants/hardware.py`/`hw_config.py`, and every slot compatibility rule has been verified against the actual GNS3 server source code (branch 2.2). This ensures:

- Slot module names match exactly (e.g., `PA-8E`, `NM-4T`, `GT96100-FE`)
- Port counts per module are accurate
- Built-in interface counts per platform are correct
- ZIP path formats match GNS3's portable project import logic (`project-files/<node_type>/<uuid>/`)
- IOU `application_id` is assigned as a mandatory unique integer per node
- IOU config files use the correct path (no `configs/` subdirectory)

---

### Structural Validator

`gns3project_validator.py` performs 11 deep validation checks on any `.gns3project` file:

1. ZIP structure (project.gns3 exists, file paths correct)
2. JSON schema conformity (revision 9, required keys)
3. Node validation (required fields, legal node types)
4. Dynamips compatibility matrix (platform ↔ slot modules)
5. Port reference integrity (link ports exist on referenced nodes)
6. Config file path consistency (paths in properties match files in ZIP)
7. Template ID format (null or valid UUID)
8. Compute cross-referencing
9. Switch VLAN sanity (access VLANs 1-4094, trunk dot1q)
10. Link integrity (no duplicates, no self-links)
11. UUID format validation

```bash
python gns3project_validator.py <file.gns3project>
python gns3project_validator.py <file.gns3project> --verbose
```

### Golden End-to-End Test

A regression test verifies export + validator against a known-good fixture:

```bash
python -m unittest tests.test_golden_export
```

This protects the core promise: generated `.gns3project` remains structurally importable.

### Post-Generation Report

Each run writes `output/generation_report.json` containing:

1. Request text and timestamp
2. Effective preflight profile used
3. Compatibility findings and design-review assumptions
4. Output paths (`_topology.json`, `final_topology.json`, `.gns3project`)
5. Validator result (skipped/pass/fail)

---

## Export Format

The `.gns3project` export produces a GNS3 revision 9 portable project ZIP:

```
my_network.gns3project
├── project.gns3                                            # Main topology JSON
├── project-files/dynamips/<uuid-1>/configs/startup-config.cfg  # Dynamips startup config
├── project-files/dynamips/<uuid-1>/configs/private-config.cfg  # Dynamips private config
├── project-files/iou/<uuid-2>/startup-config.cfg           # IOU startup config (no configs/ prefix)
├── project-files/vpcs/<uuid-3>/startup.vpc                 # VPCS startup script
└── project-files/<node_type>/<uuid-4>/                     # Node directory (for structure)
```

The `project.gns3` JSON follows the exact schema that GNS3 produces when exporting portable projects, including:

- Deterministic UUID5 node/link IDs
- Canvas coordinates grouped by device role (routers center, switches above/below, hosts at periphery)
- Inline config content stripped and moved to ZIP files with correct `project-files/<node_type>/<uuid>/` paths
- Path references (`startup_config`, `private_config`) left in properties
- `template_id: null` for portable offline projects
- `status: "stopped"`, `console_auto_start: false` for clean import
- IOU nodes with unique `application_id` integer fields
- Dynamic label y-position computation matching GNS3's actual formula

---

## Configuration Reference

### Appliance Catalog

The built-in appliance catalog (`appliance_catalog.py`) defines mandatory creation properties for each supported device:

| Appliance | Type | Key Properties |
|-----------|------|----------------|
| Cisco 7200 | dynamips | platform=c7200, ram=512, slot0=PA-FE-TX |
| Cisco 3745 | dynamips | platform=c3745, ram=256, slot0=GT96100-FE |
| IOU L3 | iou | ethernet_adapters=2, serial_adapters=0 |
| IOU L2 | iou | ethernet_adapters=1, slot0=l2 |
| VPCS | vpcs | console_type=telnet |
| Ethernet Switch | ethernet_switch | console_type=none |
| Ethernet Hub | ethernet_hub | — |

Users can override or extend the catalog by providing a JSON overlay file:

```python
from appliance_catalog import load_catalog

catalog = load_catalog("my_custom_appliances.json")
```

### Dynamips Module Catalogue

`hw_config.py` maintains a complete catalogue of Dynamips expansion modules:

**Ethernet modules:** PA-8E (8 ports), PA-4E (4 ports), PA-FE-TX (1 port), NM-4E (4 ports), NM-1E (1 port), GT96100-FE (2 ports)

**Serial modules:** PA-4T+ (4 ports), PA-8T (8 ports), NM-4T (4 ports)

The hardware injector automatically selects the correct module type based on whether a link is Ethernet or serial, and computes how many slots are needed to satisfy the link count.

### IOU Configuration

IOU (IOS on Unix) nodes use a different expansion model from Dynamips:

- Each IOU adapter provides exactly **4 ports** (`IOU_PORTS_PER_ADAPTER = 4`)
- Expansion is count-based: `ethernet_adapters` and `serial_adapters` are integer properties
- Maximum 16 adapters per type (`IOU_MAX_ADAPTERS = 16`)
- Each IOU node requires a unique `application_id` integer

---

## Known Issues & Roadmap

### Recently Completed (V3.3+)

- ✅ **Security profiles** ("none", "basic", "enterprise") — topology and config hardening rules injected via LLM prompts
- ✅ **LLM utilities consolidation** — `llm_utils.py` is SSOT for client, retry, JSON extraction
- ✅ **Constants SSOT** — `constants/` package is authoritative; no more drift
- ✅ **Config review export** — `--configs DIR` exports raw configs for pre-GNS3 review
- ✅ **VLAN patching guarantee** — `topology_finalizer.apply_switch_port_patches()` runs even with `--no-phase2`

### Pending Code Fixes (Phase 4+)

Most previously documented constant-drift issues were resolved by migrating shared values to `constants/`.

Remaining work should focus on behavior-level hardening (integration tests, broader fixture coverage, and any platform-specific edge cases uncovered during validation).

### Planned Improvements

- **Remove dead code**: Delete any unused legacy modules (live deployment remnants if present)
- **Expand security profiles**: Add more specialized archetypes (e.g., "industrial", "healthcare")
- **Topology edit mode UI**: Interactive editing of existing topologies via natural language (logic in `ai_agent.py`, needs UI)

---

## License

This project is proprietary software. All rights reserved.
