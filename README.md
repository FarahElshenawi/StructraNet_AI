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
- [Streamlit Web Interface](#streamlit-web-interface)
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

Structranet AI uses a **two-phase, multi-agent pipeline** that separates logical design from physical configuration:

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
| 1/6 | User input | CLI argument or interactive prompt |
| 2/6 | `ai_agent` | LLM generates `TopologyRequest` (nodes + logical connections) |
| 3/6 | `port_assigner` → `hw_config` | Deterministic port assignment + hardware slot injection |
| 4/6 | `config_agent` | LLM generates software configs (IPs, routing, startup scripts); includes VLAN switch-port patching via `topology_finalizer` |
| 5/6 | `gns3_exporter` | Convert final topology JSON to portable `.gns3project` ZIP |
| 6/6 | `gns3project_validator` | Run 11 structural checks to ensure import safety |

---

## Project Structure

```
structranet-ai/
├── main.py                     # Grand orchestrator — 6-step CLI pipeline
│
├── ai_agent.py                 # Phase 1: LLM topology generation + edit mode
├── config_agent.py             # Phase 2: LLM software config generation
├── schema.py                   # Pydantic models (TopologyRequest, GNS3Project, etc.)
│
├── port_assigner.py            # Deterministic adapter/port number assignment
├── hw_config.py                # Hardware injection (slots, adapters, ports_mapping)
├── topology_finalizer.py       # VLAN switch port patching (trunk/access)
├── context_builder.py          # Configuration brief builder + port name resolution
│
├── constants/                  # Shared constants package (single source of truth)
│   ├── gns3.py                 # GNS3 format constants
│   ├── hardware.py             # Hardware and node-type constants
│   ├── appliances.py           # Built-in appliance catalog constants
│   ├── phase2.py               # Phase 2 safe-merge constants
│   └── ai.py                   # AI pipeline constants (retry/limits)
├── appliance_catalog.py        # Static appliance definitions (Cisco 7200, IOU, VPCS, etc.)
│
├── gns3_exporter.py            # .gns3project ZIP archive packaging + verification
│
├── gns3project_validator.py    # Deep structural validator for .gns3project files
│
└── output/                     # Generated topology files
    ├── _topology.json          # Phase 1 output (hardware-injected)
    └── final_topology.json     # Phase 2 output (software configs merged)
```

### Module Responsibilities

| Module | Role | Key Functions |
|--------|------|---------------|
| `main.py` | Entry point & pipeline orchestration | `parse_args()`, `validate_against_inventory()`, `main()` |
| `ai_agent.py` | LLM topology design | `generate_network_topology()`, `process_and_save_topology()`, `generate_edited_topology()` |
| `config_agent.py` | LLM config generation | `run_phase2()`, `safe_merge_configs()` (Three-Gate Safe Merge) |
| `schema.py` | Data contracts | `TopologyRequest`, `GNS3Project`, `validate_topology()`, `validate_topology_request()` |
| `port_assigner.py` | Port number math | `assign_ports()`, `build_topology_from_request()` |
| `hw_config.py` | Hardware expansion | `inject_hardware_config()` — Dynamips slots, IOU adapters, QEMU adapters, switch ports_mapping |
| `topology_finalizer.py` | VLAN switching | `apply_switch_port_patches()` — trunk/access/dot1q port rewrites |
| `context_builder.py` | LLM context builder | `build_configuration_brief()`, `resolve_port_name()`, `build_segments()` |
| `constants/gns3.py` | Shared GNS3 constants | `GNS3_REVISION`, `FILE_CONFIG_TRIPLETS`, `SYMBOL`, `PORT_NAME_FORMAT`, etc. |
| `constants/hardware.py` | Shared hardware constants | Dynamips module tables, adapter limits, node type sets |
| `constants/phase2.py` | Phase 2 merge constants | `SOFTWARE_CONFIG_KEYS`, `ALLOWED_VALUE_TYPES` |
| `constants/ai.py` | AI generation constants | `MAX_RETRIES`, prompt-side link-limit tables |
| `constants/appliances.py` | Appliance defaults constants | `APPLIANCE_CATALOG` |
| `appliance_catalog.py` | Template defaults | `get_appliance()`, `load_catalog()` with user overlay support |
| `gns3_exporter.py` | ZIP packaging | `export_project()`, `export_topology()`, `verify_archive()` |
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

# Skip Phase 2 (software configs)
python main.py --request "3-router topology" --no-phase2

# Custom .gns3project output path
python main.py --request "3-router topology" --project-output output/my_lab.gns3project

# Skip validator (not recommended)
python main.py --request "3-router topology" --no-validate
```

**Programmatic export:**
```python
from gns3_exporter import export_topology

# Load the final topology
import json
with open("output/final_topology.json") as f:
    topology = json.load(f)

# Export as .gns3project ZIP
path = export_topology(topology, "my_network.gns3project")
print(f"Exported to: {path}")
# Import: GNS3 GUI → File → Import portable project
```

---

## Usage

### CLI Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--request` | `-r` | Network description (skips interactive prompt) |
| `--output` | `-o` | Output JSON file path |
| `--no-phase2` | | Skip Phase 2 (software configuration generation) |
| `--project-output` | | Output `.gns3project` path |
| `--no-validate` | | Skip post-export structural validation |

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

### Post-Export Verification

The `gns3_exporter.verify_archive()` function provides built-in validation after every export:

1. The file exists and is a valid ZIP archive
2. `project.gns3` is present at the archive root
3. `project.gns3` is valid JSON with expected top-level keys
4. Node directories exist under `project-files/`
5. No excluded files (captures, logs, snapshots) are present

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

**Serial modules:** PA-4T+ (4 ports), NM-4T (4 ports), NM-1T (1 port)

The hardware injector automatically selects the correct module type based on whether a link is Ethernet or serial, and computes how many slots are needed to satisfy the link count.

### IOU Configuration

IOU (IOS on Unix) nodes use a different expansion model from Dynamips:

- Each IOU adapter provides exactly **4 ports** (`IOU_PORTS_PER_ADAPTER = 4`)
- Expansion is count-based: `ethernet_adapters` and `serial_adapters` are integer properties
- Maximum 16 adapters per type (`IOU_MAX_ADAPTERS = 16`)
- Each IOU node requires a unique `application_id` integer

---

## Known Issues & Roadmap

### Pending Code Fixes (Phase 4)

Most previously documented constant-drift issues were resolved by migrating shared values to `constants/`.

Remaining work should focus on behavior-level hardening (integration tests, broader fixture coverage, and any platform-specific edge cases uncovered during validation).

### Planned Improvements
- **Derive Dynamips max ports from hw_config**: Remove hardcoded `_DYNAMIPS_MAX_PORTS` from `schema.py`, compute from `hw_config.DYNAMIPS_SLOT_MODULES`
- **Remove dead code**: Delete `config_extractor.py`, `assembler.py`, `gns3_fetcher.py` (live deployment remnants)
- **Full LLM retry with error feedback**: Feed Pydantic validation errors back to the LLM for self-correction (partially implemented)
- **Topology edit mode**: Interactive editing of existing topologies via natural language (implemented in `ai_agent.py`, needs UI integration)

---

## License

This project is proprietary software. All rights reserved.
