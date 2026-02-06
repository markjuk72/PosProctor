#!/usr/bin/env python3
"""
Commander Analysis Tool

Standalone stateless script for one-off analysis of Verifone Commander API data.
Queries various endpoints and displays comprehensive device and tank information.

Usage:
    python commander_analyze.py --ip <commander_ip> --username <user> --password <pass>
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p mypassword
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p mypassword --json
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p mypassword --raw
"""

import argparse
import json
import sys
import requests
import urllib3
from lxml import etree
from datetime import datetime

# Suppress SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CommanderAnalyzer:
    """Lightweight Commander API client for analysis."""

    def __init__(self, ip: str, username: str, password: str, timeout: int = 30):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.token = None

    def authenticate(self) -> bool:
        """Authenticate and get session token."""
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            xml = etree.fromstring(r.content)
            self.token = xml.findtext(".//cookie")
            return self.token is not None
        except Exception as e:
            print(f"Authentication failed: {e}", file=sys.stderr)
            return False

    def _get(self, cmd: str, extra_params: str = "") -> bytes | None:
        """Make authenticated GET request."""
        if not self.token:
            return None
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd={cmd}&cookie={self.token}{extra_params}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"Request failed ({cmd}): {e}", file=sys.stderr)
            return None

    def get_forecourt_diagnostics(self) -> bytes | None:
        """Get forecourt diagnostics (pumps, DCRs, controller)."""
        return self._get("vforecourtdiagnostics")

    def get_payment_diagnostics(self) -> bytes | None:
        """Get payment diagnostics (FEPs, pinpads)."""
        return self._get("vpaymentdiagnostics")

    def get_pos_diagnostics(self) -> bytes | None:
        """Get POS terminal diagnostics."""
        return self._get("vposdiagnostics")

    def get_tank_monitor(self) -> bytes | None:
        """Get tank monitor data."""
        return self._get("vrubyrept", "&reptname=tankMonitor&period=1&reptnum=1")

    def get_system_info(self) -> bytes | None:
        """Get system information."""
        return self._get("vsysteminfo")

    def get_site_info(self) -> bytes | None:
        """Get site configuration."""
        return self._get("vsiteinfo")


def parse_forecourt(xml_content: bytes) -> dict:
    """Parse forecourt diagnostics XML."""
    result = {
        "controller": {"status": "unknown"},
        "pumps": [],
        "dcrs": [],
        "price_displays": []
    }

    if not xml_content:
        return result

    try:
        xml = etree.fromstring(xml_content)

        # Check for fault
        fault = xml.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
        if fault is not None:
            fault_str = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}faultstring", "Unknown")
            result["error"] = fault_str
            return result

        # Controller
        for tag in ["controller", "Controller"]:
            ctrl = xml.find(f".//{tag}")
            if ctrl is not None:
                result["controller"] = {
                    "status": ctrl.get("status", "unknown"),
                    "type": ctrl.get("type", "")
                }
                break

        # Fueling points (pumps and DCRs)
        for fp in xml.findall(".//fuelingPoint"):
            fp_id = fp.get("sysid", "?")

            pump = fp.find(".//device[@type='Pump']")
            if pump is not None:
                result["pumps"].append({
                    "id": fp_id,
                    "status": pump.get("status", "unknown"),
                    "available": pump.get("isAvailable", "unknown"),
                    "model": pump.get("model", "")
                })

            dcr = fp.find(".//device[@type='DCR']")
            if dcr is not None:
                result["dcrs"].append({
                    "id": fp_id,
                    "status": dcr.get("status", "unknown"),
                    "available": dcr.get("isAvailable", "unknown"),
                    "model": dcr.get("model", "")
                })

        # Price displays
        for dev in xml.findall(".//device[@type='Fuel Price Display']"):
            result["price_displays"].append({
                "id": dev.get("id", "?"),
                "status": dev.get("status", "unknown"),
                "available": dev.get("isAvailable", "unknown")
            })

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def parse_payment(xml_content: bytes) -> dict:
    """Parse payment diagnostics XML."""
    result = {
        "feps": [],
        "pinpads": []
    }

    if not xml_content:
        return result

    try:
        xml = etree.fromstring(xml_content)

        # FEPs
        for fep in xml.findall(".//fepDetail"):
            fep_data = {
                "name": fep.get("fepName", "Unknown"),
                "is_primary": fep.get("isPrimary", "false").lower() == "true",
                "connected": fep.findtext("connectionStatus", "unknown"),
                "host": fep.findtext("hostAddress", ""),
                "port": fep.findtext("portNumber", "")
            }
            result["feps"].append(fep_data)

        # Pinpads
        for pp in xml.findall(".//pinpadDetail"):
            result["pinpads"].append({
                "id": pp.get("popID", "?"),
                "workstation": pp.findtext("workstationName", "Unknown"),
                "connected": pp.findtext("connectionStatus", "unknown"),
                "type": pp.findtext("pinpadType", "")
            })

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def parse_pos(xml_content: bytes) -> dict:
    """Parse POS diagnostics XML."""
    result = {"terminals": []}

    if not xml_content:
        return result

    try:
        xml = etree.fromstring(xml_content)

        for term in xml.findall(".//posTerminal"):
            result["terminals"].append({
                "id": term.get("sysid", "?"),
                "type": term.get("type", "Unknown"),
                "status": term.get("status", "unknown")
            })

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def parse_tanks(xml_content: bytes) -> dict:
    """Parse tank monitor XML."""
    result = {
        "tanks": [],
        "alarms": [],
        "alarm_history": []
    }

    if not xml_content:
        return result

    try:
        xml = etree.fromstring(xml_content)

        # Check for fault
        fault = xml.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
        if fault is not None:
            fault_str = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}faultstring", "Unknown")
            message = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}message", "")
            result["error"] = f"{fault_str}: {message}"
            return result

        # Tank inventory
        for inv in xml.iter():
            if "inventoryInfo" in inv.tag:
                tank_data = {}
                for child in inv:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    tag_lower = tag.lower()

                    if tag_lower == "fueltank":
                        tank_data["id"] = child.get("sysid", "?")
                        tank_data["product"] = (child.text or "").strip()
                    elif tag_lower in ["fuelvolume", "volume"]:
                        tank_data["volume_gal"] = float(child.text or 0)
                    elif tag_lower in ["fuellvl", "level"]:
                        tank_data["level_in"] = float(child.text or 0)
                    elif tag_lower in ["fueltemperature", "temperature"]:
                        tank_data["temp_f"] = float(child.text or 0)
                    elif tag_lower in ["waterlvl", "water"]:
                        tank_data["water_in"] = float(child.text or 0)
                    elif tag_lower == "ullage":
                        tank_data["ullage_gal"] = float(child.text or 0)
                    elif tag_lower in ["fuelcapacity", "capacity"]:
                        tank_data["capacity_gal"] = float(child.text or 0)

                if tank_data.get("id"):
                    # Calculate fill percentage
                    vol = tank_data.get("volume_gal", 0)
                    cap = tank_data.get("capacity_gal", 0)
                    if cap > 0:
                        tank_data["fill_pct"] = round((vol / cap) * 100, 1)
                    result["tanks"].append(tank_data)

        # Alarm status
        for status in xml.iter():
            if "intTankAlarmStatus" in status.tag:
                alarm_data = {"flags": {}}
                for child in status:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

                    if tag.lower() == "fueltank":
                        alarm_data["tank_id"] = child.get("sysid", "?")
                        alarm_data["product"] = (child.text or "").strip()
                    elif tag.lower() == "inttankflags":
                        for flag in child:
                            flag_tag = flag.tag.split("}")[-1] if "}" in flag.tag else flag.tag
                            alarm_data["flags"][flag_tag.lower()] = (flag.text or "").upper() == "ON"

                if alarm_data.get("tank_id"):
                    result["alarms"].append(alarm_data)

        # Alarm history
        for hist in xml.iter():
            if "internalTankAlarms" in hist.tag:
                tank_id = None
                product = None
                for child in hist:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

                    if tag.lower() == "fueltank":
                        tank_id = child.get("sysid", "?")
                        product = (child.text or "").strip()
                    elif tag.lower() == "internalalarm":
                        alarm_type = None
                        alarm_date = None
                        for ac in child:
                            ac_tag = ac.tag.split("}")[-1] if "}" in ac.tag else ac.tag
                            if "alarmtypedescription" in ac_tag.lower():
                                alarm_type = ac.text
                            elif "alarmdate" in ac_tag.lower():
                                alarm_date = ac.text

                        if alarm_type:
                            result["alarm_history"].append({
                                "tank_id": tank_id,
                                "product": product,
                                "type": alarm_type,
                                "date": alarm_date
                            })

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def parse_system_info(xml_content: bytes) -> dict:
    """Parse system info XML."""
    result = {}

    if not xml_content:
        return result

    try:
        xml = etree.fromstring(xml_content)

        # Extract common fields
        for elem in xml.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if elem.text and elem.text.strip():
                result[tag] = elem.text.strip()

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def format_status(status: str) -> str:
    """Format status with color indicator."""
    s = status.lower()
    if s in ["online", "true", "1"]:
        return f"ONLINE"
    elif s in ["offline", "false", "0"]:
        return f"OFFLINE"
    return status.upper()


def print_report(data: dict, commander_ip: str):
    """Print formatted analysis report."""
    print("=" * 70)
    print(f"COMMANDER ANALYSIS REPORT")
    print(f"IP: {commander_ip}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # System Info
    if data.get("system_info"):
        print("\n--- SYSTEM INFO ---")
        si = data["system_info"]
        for key in ["siteName", "siteAddress", "softwareVersion", "softwareBuild", "serialNumber"]:
            if key in si:
                print(f"  {key}: {si[key]}")

    # Forecourt
    fc = data.get("forecourt", {})
    if fc.get("error"):
        print(f"\n--- FORECOURT (ERROR) ---")
        print(f"  Error: {fc['error']}")
    else:
        print("\n--- FORECOURT ---")
        ctrl = fc.get("controller", {})
        print(f"  Controller: {format_status(ctrl.get('status', 'unknown'))}")

        if fc.get("pumps"):
            print(f"\n  Pumps ({len(fc['pumps'])}):")
            for p in fc["pumps"]:
                status = format_status(p.get("status", "unknown"))
                avail = "Avail" if p.get("available", "").lower() == "true" else "N/A"
                print(f"    Pump {p['id']}: {status} ({avail}) {p.get('model', '')}")

        if fc.get("dcrs"):
            print(f"\n  DCRs ({len(fc['dcrs'])}):")
            for d in fc["dcrs"]:
                status = format_status(d.get("status", "unknown"))
                avail = "Avail" if d.get("available", "").lower() == "true" else "N/A"
                print(f"    DCR {d['id']}: {status} ({avail})")

        if fc.get("price_displays"):
            print(f"\n  Price Displays ({len(fc['price_displays'])}):")
            for pd in fc["price_displays"]:
                status = format_status(pd.get("status", "unknown"))
                print(f"    Display {pd['id']}: {status}")

    # Payment
    pay = data.get("payment", {})
    print("\n--- PAYMENT SYSTEMS ---")

    if pay.get("feps"):
        print(f"\n  FEPs ({len(pay['feps'])}):")
        for f in pay["feps"]:
            conn = "Connected" if f.get("connected", "").lower() == "true" else "Disconnected"
            primary = " [PRIMARY]" if f.get("is_primary") else ""
            print(f"    {f['name']}: {conn}{primary}")
            if f.get("host"):
                print(f"      Host: {f['host']}:{f.get('port', '')}")

    if pay.get("pinpads"):
        print(f"\n  Pinpads ({len(pay['pinpads'])}):")
        for pp in pay["pinpads"]:
            conn = "Connected" if pp.get("connected", "").lower() == "true" else "Disconnected"
            print(f"    Pinpad {pp['id']} ({pp['workstation']}): {conn}")

    # POS
    pos = data.get("pos", {})
    if pos.get("terminals"):
        print(f"\n--- POS TERMINALS ({len(pos['terminals'])}) ---")
        for t in pos["terminals"]:
            status = format_status(t.get("status", "unknown"))
            print(f"    Terminal {t['id']} ({t['type']}): {status}")

    # Tanks
    tanks = data.get("tanks", {})
    if tanks.get("error"):
        print(f"\n--- TANKS (ERROR) ---")
        print(f"  {tanks['error']}")
    elif tanks.get("tanks"):
        print(f"\n--- TANK INVENTORY ({len(tanks['tanks'])}) ---")
        for t in tanks["tanks"]:
            fill = t.get("fill_pct", 0)
            fill_bar = "#" * int(fill / 5) + "-" * (20 - int(fill / 5))
            print(f"\n  Tank {t.get('id', '?')}: {t.get('product', 'Unknown')}")
            print(f"    Volume:  {t.get('volume_gal', 0):,.0f} gal / {t.get('capacity_gal', 0):,.0f} gal")
            print(f"    Fill:    [{fill_bar}] {fill:.1f}%")
            print(f"    Level:   {t.get('level_in', 0):.2f} in")
            print(f"    Temp:    {t.get('temp_f', 0):.1f} F")
            print(f"    Water:   {t.get('water_in', 0):.2f} in")
            print(f"    Ullage:  {t.get('ullage_gal', 0):,.0f} gal")

        # Alarm status
        if tanks.get("alarms"):
            print(f"\n--- TANK ALARMS ---")
            has_active = False
            for a in tanks["alarms"]:
                active_flags = [k for k, v in a.get("flags", {}).items() if v]
                if active_flags:
                    has_active = True
                    print(f"  Tank {a.get('tank_id', '?')} ({a.get('product', '')}): {', '.join(active_flags).upper()}")
            if not has_active:
                print("  No active alarms")

        # Alarm history
        if tanks.get("alarm_history"):
            print(f"\n--- ALARM HISTORY (Recent) ---")
            for h in tanks["alarm_history"][:10]:  # Show last 10
                print(f"  Tank {h.get('tank_id', '?')}: {h.get('type', 'Unknown')} ({h.get('date', 'Unknown date')})")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Verifone Commander API data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p secret
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p secret --json
    python commander_analyze.py --ip 192.168.1.100 -u posproctor -p secret --raw
        """
    )
    parser.add_argument("--ip", "-i", required=True, help="Commander IP address")
    parser.add_argument("--username", "-u", required=True, help="Username")
    parser.add_argument("--password", "-p", required=True, help="Password")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Request timeout (default: 30s)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--raw", "-r", action="store_true", help="Output raw XML responses")
    parser.add_argument("--endpoint", "-e", choices=["all", "forecourt", "payment", "pos", "tanks", "system"],
                        default="all", help="Specific endpoint to query (default: all)")

    args = parser.parse_args()

    # Create analyzer
    analyzer = CommanderAnalyzer(args.ip, args.username, args.password, args.timeout)

    # Authenticate
    if not args.json:
        print(f"Connecting to {args.ip}...", file=sys.stderr)
    if not analyzer.authenticate():
        print("Failed to authenticate. Check credentials and connectivity.", file=sys.stderr)
        sys.exit(1)
    if not args.json:
        print("Authenticated successfully.", file=sys.stderr)

    # Collect data based on endpoint selection
    raw_data = {}
    parsed_data = {}

    endpoints = {
        "forecourt": (analyzer.get_forecourt_diagnostics, parse_forecourt),
        "payment": (analyzer.get_payment_diagnostics, parse_payment),
        "pos": (analyzer.get_pos_diagnostics, parse_pos),
        "tanks": (analyzer.get_tank_monitor, parse_tanks),
        "system": (analyzer.get_system_info, parse_system_info),
    }

    if args.endpoint == "all":
        queries = endpoints.keys()
    else:
        queries = [args.endpoint]

    for name in queries:
        getter, parser_func = endpoints[name]
        if not args.json:
            print(f"Fetching {name}...", file=sys.stderr)
        xml_content = getter()
        raw_data[name] = xml_content
        if xml_content:
            parsed_data[name] = parser_func(xml_content)
        else:
            parsed_data[name] = {"error": "No data returned"}

    if not args.json:
        print("", file=sys.stderr)  # Blank line before report

    # Output
    if args.raw:
        for name, content in raw_data.items():
            print(f"\n{'='*60}")
            print(f"RAW XML: {name.upper()}")
            print("=" * 60)
            if content:
                try:
                    # Pretty print XML
                    xml = etree.fromstring(content)
                    print(etree.tostring(xml, pretty_print=True, encoding="unicode"))
                except Exception:
                    print(content.decode("utf-8", errors="replace"))
            else:
                print("(no data)")
    elif args.json:
        # Convert to JSON-serializable format
        output = {
            "ip": args.ip,
            "timestamp": datetime.now().isoformat(),
            "system_info": parsed_data.get("system", {}),
            "forecourt": parsed_data.get("forecourt", {}),
            "payment": parsed_data.get("payment", {}),
            "pos": parsed_data.get("pos", {}),
            "tanks": parsed_data.get("tanks", {})
        }
        print(json.dumps(output, indent=2))
    else:
        print_report({
            "system_info": parsed_data.get("system", {}),
            "forecourt": parsed_data.get("forecourt", {}),
            "payment": parsed_data.get("payment", {}),
            "pos": parsed_data.get("pos", {}),
            "tanks": parsed_data.get("tanks", {})
        }, args.ip)


if __name__ == "__main__":
    main()
