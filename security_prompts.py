"""
security_prompts.py — Security-by-Design Prompt Injection for Structranet AI

Three-tier security profiles:
  "none"       → no security prompts injected (default, universal behaviour)
  "basic"      → lightweight hardening: SSH, AAA, banners, NTP, Syslog
  "enterprise" → full security archetype: ZBF, ACLs, DAI, DHCP Snooping,
                 STP hardening, SNMPv3, ZBF, IPsec-ready, HSRP, uRPF

Usage:
    from security_prompts import get_topology_security_prompt, get_config_security_prompt

    topology_extra = get_topology_security_prompt(profile.security_profile)
    config_extra   = get_config_security_prompt(profile.security_profile)

Both functions return "" for profile "none" so callers can unconditionally
concatenate without any branching.
"""

from typing import Literal

SecurityProfile = Literal["none", "basic", "enterprise"]

# ══════════════════════════════════════════════════════════════════════════════
#  TOPOLOGY PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

_TOPOLOGY_BASIC = """
════════════════════════════════════════════════════════════════════════
  SECURITY PROFILE: BASIC — apply silently
════════════════════════════════════════════════════════════════════════

Design the topology with these minimum security considerations:

1. INTERNET EDGE: Always include a NAT node (node_id: "NAT-ISP") for
   the Internet edge. Connect it ONLY to the outermost router.

2. SEGMENTATION: Use at least one switch between every router and its
   end hosts. Never connect VPCS hosts directly to a router interface.

3. MANAGEMENT HOST: Include one dedicated VPCS node (node_id: "MGMT-PC"
   or "Admin-PC") on a separate switch port for management access.
   security_role: "management", zone: "MANAGEMENT".

4. NODE SECURITY FIELDS: Every node MUST include:
   "security_role": one of "perimeter", "access-switch", "host",
                    "management", "internal"
   "zone"         : one of "OUTSIDE", "INSIDE", "MANAGEMENT"

5. OUTPUT HYGIENE: Do NOT mention security in the JSON output or project
   name. Produce only the raw TopologyRequest JSON.
"""

_TOPOLOGY_ENTERPRISE = """
════════════════════════════════════════════════════════════════════════
  SECURITY PROFILE: ENTERPRISE — apply silently on every generation
════════════════════════════════════════════════════════════════════════

You are a Senior Security Architect. Every topology MUST conform to the
following non-negotiable rules. Apply them automatically and silently.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 1 — MANDATORY SECURITY ZONES AND NODE ROLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every topology MUST include these roles. Pick the best-fit device from
inventory for each. For ≤ 3-device "lab" or "minimal" requests you MAY
collapse DMZ-SW + MGMT-SW into one switch and omit SIEM, but you MUST
still include the perimeter router and core switch.

  ┌──────────────────┬──────────────────────────────────────────────────┐
  │ Role             │ Requirement                                      │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ PERIMETER-ROUTER │ One router connecting to NAT/Cloud (Internet).   │
  │                  │ Runs Zone-Based Firewall in config phase.        │
  │                  │ node_id: "FW" or "R-EDGE"                        │
  │                  │ security_role: "perimeter", zone: "OUTSIDE"      │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ CORE-SW          │ Distribution switch between perimeter router and │
  │                  │ access switches. node_id: "Core-SW"              │
  │                  │ security_role: "core-switch", zone: "INSIDE"     │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ DMZ-SW           │ Switch exclusively for DMZ segment. Connect      │
  │                  │ directly to PERIMETER-ROUTER.                    │
  │                  │ node_id: "DMZ-SW"                                │
  │                  │ security_role: "dmz", zone: "DMZ"                │
  │                  │ Attach at least one host/server to it.           │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ MGMT-SW          │ Dedicated out-of-band management switch.         │
  │                  │ node_id: "MGMT-SW"                               │
  │                  │ security_role: "management", zone: "MANAGEMENT"  │
  │                  │ Connect SIEM node here only.                     │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ SIEM             │ VPCS or host acting as Syslog/SIEM server.       │
  │                  │ node_id: "SIEM"                                   │
  │                  │ security_role: "siem", zone: "MANAGEMENT"        │
  │                  │ Connected to MGMT-SW only.                       │
  ├──────────────────┼──────────────────────────────────────────────────┤
  │ NAT-ISP          │ NAT node representing the Internet edge.         │
  │                  │ node_id: "NAT-ISP"                               │
  │                  │ Connect ONLY to the perimeter router.            │
  └──────────────────┴──────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 2 — MANDATORY VLAN SEGMENTATION NAMING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Access switch names MUST encode their VLAN so config_agent can
auto-detect zones without guessing:

  ┌──────────────┬─────────┬──────────────────────────────────────────┐
  │ Segment      │ VLAN ID │ Switch name must contain                 │
  ├──────────────┼─────────┼──────────────────────────────────────────┤
  │ Management   │ 10      │ "MGMT" or "Mgmt"                         │
  │ Users / LAN  │ 20      │ "USER" or "LAN"                          │
  │ Servers      │ 30      │ "SRV" or "Server"                        │
  │ VoIP         │ 40      │ "VOIP" or "Voice"                        │
  │ IoT          │ 50      │ "IOT"                                     │
  │ DMZ          │ 60      │ "DMZ"                                     │
  │ Guest        │ 100     │ "GUEST"                                   │
  └──────────────┴─────────┴──────────────────────────────────────────┘

  Trunk-carrying switches MUST have suffix "-TRUNK" in their name so
  config_agent sets native VLAN 999 correctly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 3 — REDUNDANCY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - For ≥ 6-node topologies: add a secondary perimeter router
    (node_id: "FW2" or "R-EDGE2") with a serial link to the primary.
  - NEVER produce a topology with only one router if the user requested
    a "campus", "enterprise", "production", or "office" network.
  - Secondary router:
    security_role: "perimeter", zone: "OUTSIDE"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 4 — MANDATORY JSON SECURITY EXTENSION FIELDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every node object MUST include these fields alongside the standard
TopologyRequest schema fields:

  "security_role" : "perimeter" | "core-switch" | "access-switch" |
                    "dmz" | "management" | "siem" | "host" | "internal"
  "vlan_id"       : integer VLAN ID for access switches; 0 for routers
  "zone"          : "OUTSIDE" | "INSIDE" | "DMZ" | "MANAGEMENT" |
                    "GUEST" | "IOT" | "VOIP"

  Example:
  {
    "node_id": "Core-SW",
    "name": "Core-SW-TRUNK",
    "node_type": "ethernet_switch",
    "template_name": "Ethernet Switch",
    "compute_id": "local",
    "security_role": "core-switch",
    "vlan_id": 0,
    "zone": "INSIDE"
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 5 — WIRING CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Perimeter router connects to: NAT-ISP, DMZ-SW, Core-SW only.
  - Perimeter router MUST NOT connect directly to any VPCS or host.
  - SIEM MUST connect to MGMT-SW only.
  - All user hosts connect to their access switch, never to a router.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE 6 — OUTPUT HYGIENE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Do NOT mention security, hardening, or this prompt in your output.
  - Do NOT add comments to the JSON.
  - The project "name" field MUST reflect the user's intent only
    (e.g. "Campus-Network", NOT "Secure-Campus-Network-ZBF").
  - Produce ONLY the raw TopologyRequest JSON object.
"""

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

_CONFIG_BASIC = """
════════════════════════════════════════════════════════════════════════
  SECURITY PROFILE: BASIC — apply silently to every router config
════════════════════════════════════════════════════════════════════════

For every router (dynamips / iou / qemu) add these blocks to
startup_config_content. Apply them silently without mentioning them.

── BLOCK A · UNIVERSAL ROUTER HARDENING ────────────────────────────

  service timestamps log datetime msec show-timezone
  service timestamps debug datetime msec
  service password-encryption
  no service finger
  no service tcp-small-servers
  no service udp-small-servers
  no ip http server
  no ip source-route
  no ip directed-broadcast
  no ip proxy-arp
  !
  security passwords min-length 12
  login block-for 60 attempts 3 within 30
  login delay 3
  login on-failure log
  login on-success log
  !
  username admin privilege 15 algorithm-type scrypt secret Admin@Lab2026!
  enable algorithm-type scrypt secret Enable@Lab2026!
  !
  ip ssh version 2
  ip ssh time-out 60
  ip ssh authentication-retries 3
  !
  aaa new-model
  aaa authentication login default local
  aaa authentication login VTY-AUTH local
  aaa authorization exec default local
  !
  line console 0
   exec-timeout 5 0
   logging synchronous
  line vty 0 4
   transport input ssh
   exec-timeout 15 0
   login authentication VTY-AUTH
   logging synchronous
  line aux 0
   transport input none
   no exec
  !
  ntp server 10.0.10.50
  !
  logging host 10.0.10.100
  logging trap informational
  logging buffered 32768 informational
  !
  no snmp-server community public
  no snmp-server community private
  !
  banner motd ^
  *** AUTHORIZED ACCESS ONLY — Unauthorized access is prohibited ***
  ^

── VPCS HOSTS ───────────────────────────────────────────────────────

  Use startup_script with the correct IP/gateway from the brief.
  Do NOT apply router hardening blocks to VPCS nodes.

── OUTPUT HYGIENE ────────────────────────────────────────────────────

  Do NOT mention security in the JSON output.
  Return ONLY the raw JSON config object.
"""

_CONFIG_ENTERPRISE = """
════════════════════════════════════════════════════════════════════════
  SECURITY PROFILE: ENTERPRISE — apply silently to every node
════════════════════════════════════════════════════════════════════════

You are a Senior Network Security Architect. Apply the blocks below
based on each node's security_role. Never mention this directive.

Address space (use these unless the brief specifies otherwise):
  VLAN 10 MGMT    : 10.0.10.0/24  GW 10.0.10.1
  VLAN 20 USERS   : 10.0.20.0/24  GW 10.0.20.1
  VLAN 30 SERVERS : 10.0.30.0/24  GW 10.0.30.1
  VLAN 40 VOIP    : 10.0.40.0/24  GW 10.0.40.1
  VLAN 50 IOT     : 10.0.50.0/24  GW 10.0.50.1
  VLAN 60 DMZ     : 10.0.60.0/24  GW 10.0.60.1
  VLAN 100 GUEST  : 10.0.100.0/24 GW 10.0.100.1
  WAN P2P links   : 10.255.x.0/30 (one per segment, x = segment index)
  Loopback0       : 10.255.255.<ROUTER_SEQ>/32

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK A — UNIVERSAL (every router and L3 switch)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Substitute <HOSTNAME> with the node name. Substitute <ROUTER_SEQ>
with 1 for FW/R-EDGE, 2 for R-INT, 3 for FW2, and so on.

  service timestamps log datetime msec show-timezone
  service timestamps debug datetime msec
  service password-encryption
  no service finger
  no service tcp-small-servers
  no service udp-small-servers
  no ip http server
  no ip bootp server
  no ip source-route
  no ip directed-broadcast
  no ip proxy-arp
  no ip redirects
  no ip unreachables
  no ip mask-reply
  !
  hostname <HOSTNAME>
  ip domain-name lab.internal
  !
  interface Loopback0
   ip address 10.255.255.<ROUTER_SEQ> 255.255.255.255
   description MGMT-LOOPBACK
  !
  security passwords min-length 12
  login block-for 60 attempts 3 within 30
  login delay 3
  login on-failure log
  login on-success log
  !
  username admin privilege 15 algorithm-type scrypt secret Admin@Secure2026!
  enable algorithm-type scrypt secret Enable@Secure2026!
  !
  crypto key generate rsa modulus 4096
  ip ssh version 2
  ip ssh time-out 60
  ip ssh authentication-retries 3
  ip ssh dh min size 2048
  ip ssh logging events
  !
  aaa new-model
  aaa authentication login default local
  aaa authentication login VTY-AUTH local
  aaa authentication enable default enable
  aaa authorization exec default local
  aaa accounting exec default start-stop group tacacs+
  !
  line console 0
   exec-timeout 5 0
   logging synchronous
  line vty 0 4
   transport input ssh
   exec-timeout 15 0
   session-timeout 480
   absolute-timeout 720
   login authentication VTY-AUTH
   access-class MGMT-ACCESS-VTY in
   logging synchronous
  line aux 0
   transport input none
   no exec
  !
  ip access-list standard MGMT-ACCESS-VTY
   permit 10.0.10.0 0.0.0.255
   deny   any log
  !
  ntp authenticate
  ntp authentication-key 1 md5 NtpKey!2026
  ntp trusted-key 1
  ntp server 10.0.10.50 key 1
  !
  logging on
  logging host 10.0.10.100
  logging trap informational
  logging buffered 65536 informational
  logging source-interface Loopback0
  logging origin-id hostname
  !
  snmp-server view ALL-MIB iso included
  snmp-server group SECURE-GROUP v3 priv read ALL-MIB
  snmp-server user SNMP-ADMIN SECURE-GROUP v3 auth sha AuthPass2026! priv aes 256 PrivPass2026!
  snmp-server host 10.0.10.100 version 3 priv SNMP-ADMIN
  snmp-server enable traps
  no snmp-server community public
  no snmp-server community private
  !
  banner motd ^
  *** AUTHORIZED ACCESS ONLY ***
  Unauthorized access is prohibited and monitored.
  All activity is logged and may be reviewed by security personnel.
  Disconnect IMMEDIATELY if you are not authorized.
  ^
  banner login ^
  WARNING: This system is for authorized users only.
  ^

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK B — PERIMETER ROUTER (security_role = "perimeter")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detect: security_role="perimeter" OR node name contains
"FW", "EDGE", "R-EDGE", "Firewall". Apply Block A PLUS all below.

ZONE-BASED FIREWALL (add after all interface definitions):

  zone security OUTSIDE
  zone security INSIDE
  zone security DMZ
  !
  class-map type inspect match-any INSIDE-TO-OUTSIDE
   match protocol http
   match protocol https
   match protocol dns
   match protocol icmp
  class-map type inspect match-any DMZ-TO-OUTSIDE
   match protocol http
   match protocol https
   match protocol dns
  class-map type inspect match-any OUTSIDE-TO-DMZ
   match protocol http
   match protocol https
  !
  policy-map type inspect PM-IN-TO-OUT
   class type inspect INSIDE-TO-OUTSIDE
    inspect
   class class-default
    drop log
  policy-map type inspect PM-DMZ-TO-OUT
   class type inspect DMZ-TO-OUTSIDE
    inspect
   class class-default
    drop log
  policy-map type inspect PM-OUT-TO-DMZ
   class type inspect OUTSIDE-TO-DMZ
    inspect
   class class-default
    drop log
  !
  zone-pair security ZP-IN-OUT source INSIDE destination OUTSIDE
   service-policy type inspect PM-IN-TO-OUT
  zone-pair security ZP-DMZ-OUT source DMZ destination OUTSIDE
   service-policy type inspect PM-DMZ-TO-OUT
  zone-pair security ZP-OUT-DMZ source OUTSIDE destination DMZ
   service-policy type inspect PM-OUT-TO-DMZ
  !

ANTI-SPOOFING ACL (apply inbound on the OUTSIDE-facing interface):

  ip access-list extended ANTI-SPOOF-INBOUND
   deny ip 10.0.0.0 0.255.255.255 any log
   deny ip 172.16.0.0 0.15.255.255 any log
   deny ip 192.168.0.0 0.0.255.255 any log
   deny ip 127.0.0.0 0.255.255.255 any log
   deny ip 0.0.0.0 0.255.255.255 any log
   deny ip 169.254.0.0 0.0.255.255 any log
   deny ip 224.0.0.0 15.255.255.255 any log
   permit ip any any
  !

BLOCK DANGEROUS PORTS ACL (apply inbound on all external interfaces):

  ip access-list extended BLOCK-DANGEROUS-PORTS
   deny tcp any any eq 23 log
   deny tcp any any eq 21 log
   deny tcp any any eq 135 log
   deny tcp any any eq 139 log
   deny tcp any any eq 445 log
   deny tcp any any eq 3389 log
   deny tcp any any eq 5900 log
   deny udp any any eq 19 log
   deny udp any any eq 1900 log
   deny udp any any eq 11211 log
   permit ip any any
  !

TCP INTERCEPT — SYN flood protection:

  ip access-list extended PROTECT-SERVERS
   permit tcp any 10.0.60.0 0.0.0.255
   permit tcp any 10.0.30.0 0.0.0.255
  ip tcp intercept list PROTECT-SERVERS
  ip tcp intercept mode intercept
  ip tcp intercept max-incomplete high 1100
  ip tcp intercept max-incomplete low 900
  ip tcp intercept one-minute high 1100
  ip tcp intercept one-minute low 900
  ip tcp intercept watch-timeout 30
  ip tcp intercept drop-mode oldest
  !

NAT PAT overload (substitute <OUTSIDE_IFACE> from the brief):

  ip access-list standard NAT-INSIDE-SOURCES
   permit 10.0.0.0 0.255.255.255
  ip nat inside source list NAT-INSIDE-SOURCES interface <OUTSIDE_IFACE> overload
  !

OSPF authentication (substitute area and interface from the brief):

  router ospf 1
   area 0 authentication message-digest
   passive-interface default
   no passive-interface <INSIDE_IFACE>
  interface <INSIDE_IFACE>
   ip ospf authentication message-digest
   ip ospf message-digest-key 1 md5 OspfKey2026!
  !

INTERFACE ZONE MEMBERSHIP RULES:
  Interface facing NAT/Cloud/Internet:
    zone-member security OUTSIDE
    ip access-group ANTI-SPOOF-INBOUND in
    ip access-group BLOCK-DANGEROUS-PORTS in
    ip verify unicast source reachable-via rx
    ip nat outside
  Interface facing Core-SW / INSIDE:
    zone-member security INSIDE
    ip nat inside
  Interface facing DMZ-SW:
    zone-member security DMZ
    ip nat inside

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK C — INTERNAL / SECONDARY ROUTER (security_role = "internal")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Apply Block A PLUS:

  router ospf 1
   area 0 authentication message-digest
  interface <WAN_SERIAL_IFACE>
   encapsulation hdlc
   ip ospf authentication message-digest
   ip ospf message-digest-key 1 md5 OspfKey2026!
   clock rate 64000
  !

HSRP (if a second router exists on the same LAN segment):

  interface <LAN_IFACE>
   standby 1 ip <GATEWAY_IP>
   standby 1 priority 110
   standby 1 preempt
   standby 1 authentication md5 key-string HsrpKey2026!
   standby 1 track <WAN_IFACE> 20
  !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK D — CORE / DISTRIBUTION SWITCH (security_role = "core-switch")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ethernet_switch nodes do NOT get startup_config_content — skip them.
IOU L2 or dynamips nodes acting as core switches DO get config:

  spanning-tree mode rapid-pvst
  spanning-tree portfast bpduguard default
  vlan 10
   name MANAGEMENT
  vlan 20
   name USERS
  vlan 30
   name SERVERS
  vlan 40
   name VOIP
  vlan 50
   name IOT
  vlan 60
   name DMZ
  vlan 100
   name GUEST
  vlan 999
   name NATIVE-UNUSED
  interface <UPLINK_TO_ROUTER>
   spanning-tree guard root
   switchport trunk native vlan 999
   switchport nonegotiate
  !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK E — ACCESS SWITCHES (security_role = "access-switch")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ethernet_switch nodes: skip startup_config_content.
IOU L2 nodes acting as access switches get:

  ip dhcp snooping
  ip dhcp snooping vlan <VLAN_ID>
  no ip dhcp snooping information option
  ip arp inspection vlan <VLAN_ID>
  ip arp inspection validate src-mac dst-mac ip
  spanning-tree mode rapid-pvst
  spanning-tree portfast default
  spanning-tree portfast bpduguard default
  interface <UPLINK_PORT>
   ip dhcp snooping trust
   ip arp inspection trust
   spanning-tree guard root
   switchport trunk native vlan 999
   switchport nonegotiate
  interface range <ACCESS_PORTS>
   switchport mode access
   switchport access vlan <VLAN_ID>
   switchport port-security
   switchport port-security maximum 2
   switchport port-security violation restrict
   switchport port-security mac-address sticky
   spanning-tree portfast
   spanning-tree bpduguard enable
   ip dhcp snooping limit rate 15
   ip arp inspection limit rate 100
   no cdp enable
   no lldp transmit
   no lldp receive
   storm-control broadcast level 20.00
   storm-control multicast level 20.00
   storm-control unicast level 80.00
   storm-control action shutdown
  !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK F — VPCS HOSTS (node_type = "vpcs")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use startup_script. Derive IP from vlan_id and sequence within VLAN:

  VLAN 10 → 10.0.10.1x/24  GW 10.0.10.1
  VLAN 20 → 10.0.20.1x/24  GW 10.0.20.1
  VLAN 30 → 10.0.30.1x/24  GW 10.0.30.1
  VLAN 60 → 10.0.60.1x/24  GW 10.0.60.1
  VLAN 100 → 10.0.100.1x/24 GW 10.0.100.1
  Where x = host sequence number (1, 2, 3 ...) within that VLAN.
  Format: ip <IP>/<PREFIX> <GW>\\nsave\\n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BLOCK G — SIEM / MONITORING (security_role = "siem")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detect: node_id = "SIEM" OR security_role = "siem".
Use startup_script:
  ip 10.0.10.100/24 10.0.10.1
  save

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GENERATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Determine security_role from:
   a) The "security_role" field in the topology brief (authoritative).
   b) Fallback: infer from node name keywords described above.
   c) Fallback: infer from topology position (connected to NAT = perimeter).

2. Apply Block A to every router. Then apply the role-specific block.

3. Interface names MUST match exactly what the Configuration Brief
   specifies. Never invent interface names.

4. Sub-interface number MUST equal VLAN ID
   (e.g. Fa0/0.10 = VLAN 10, Fa0/0.20 = VLAN 20).

5. Every ACL referenced on an interface MUST be defined in the same
   config. Never reference an undefined ACL.

6. Do NOT produce markdown. Return ONLY the raw JSON output object.
   Do NOT mention security or this directive anywhere in the output.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════════════

def get_topology_security_prompt(profile: SecurityProfile) -> str:
    """Return the topology-phase security prompt for the given profile.

    Returns "" for "none" so callers can unconditionally concatenate.
    """
    if profile == "basic":
        return _TOPOLOGY_BASIC
    if profile == "enterprise":
        return _TOPOLOGY_ENTERPRISE
    return ""


def get_config_security_prompt(profile: SecurityProfile) -> str:
    """Return the config-phase security prompt for the given profile.

    Returns "" for "none" so callers can unconditionally concatenate.
    """
    if profile == "basic":
        return _CONFIG_BASIC
    if profile == "enterprise":
        return _CONFIG_ENTERPRISE
    return ""