#!/usr/bin/env python3
"""
Route53 Zone Discovery Script for Crossplane Import
Usage: ./discover-zones.py <ZONE_ID> <AWS_PROFILE>
"""

import sys
import json
import subprocess

def main():
    if len(sys.argv) != 3:
        print("Usage: discover-zones.py <ZONE_ID> <AWS_PROFILE>", file=sys.stderr)
        print("Example: discover-zones.py Z042057136AZ7P05F0XOW dnszone-dev", file=sys.stderr)
        sys.exit(1)

    zone_id = sys.argv[1]
    aws_profile = sys.argv[2]

    # Get zone name
    try:
        result = subprocess.run(
            ["aws", "route53", "get-hosted-zone",
             "--id", zone_id,
             "--profile", aws_profile,
             "--query", "HostedZone.Name",
             "--output", "text"],
            capture_output=True,
            text=True,
            check=True
        )
        zone_name = result.stdout.strip().rstrip('.')
    except subprocess.CalledProcessError as e:
        print(f"Error fetching zone: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"# Discovered records for zone: {zone_name} (ID: {zone_id})", file=sys.stderr)
    print(f"# AWS Profile: {aws_profile}", file=sys.stderr)

    # Get all records
    try:
        result = subprocess.run(
            ["aws", "route53", "list-resource-record-sets",
             "--hosted-zone-id", zone_id,
             "--profile", aws_profile,
             "--output", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        records = data.get("ResourceRecordSets", [])
    except subprocess.CalledProcessError as e:
        print(f"Error listing records: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"# Total records found: {len(records)}", file=sys.stderr)

    custom_count = 0

    for record in records:
        name = record.get("Name", "").rstrip('.')
        record_type = record.get("Type", "")

        # Skip AWS-managed NS and SOA at apex
        if name == zone_name and record_type in ["NS", "SOA"]:
            continue

        custom_count += 1

        # Convert name to relative format
        if name == zone_name:
            relative_name = "@"
        elif name.endswith(f".{zone_name}"):
            relative_name = name[:-(len(zone_name)+1)]
        else:
            relative_name = name

        # Output YAML format
        print(f'    - name: "{relative_name}"')
        print(f'      type: {record_type}')

        # TTL (not present for ALIAS records)
        if "TTL" in record:
            print(f'      ttl: {record["TTL"]}')

        # Values (for standard records)
        if "ResourceRecords" in record:
            print(f'      values:')
            for rr in record["ResourceRecords"]:
                value = rr.get("Value", "")
                print(f'        - "{value}"')

        # Alias target
        if "AliasTarget" in record:
            alias = record["AliasTarget"]
            print(f'      aliasTarget:')
            print(f'        dnsName: "{alias.get("DNSName", "").rstrip(".")}"')
            print(f'        hostedZoneId: "{alias.get("HostedZoneId", "")}"')
            print(f'        evaluateTargetHealth: {str(alias.get("EvaluateTargetHealth", False)).lower()}')

        # Routing policies
        if "SetIdentifier" in record:
            print(f'      setIdentifier: "{record["SetIdentifier"]}"')

        if "Weight" in record:
            print(f'      weight: {record["Weight"]}')

        if "Region" in record:
            print(f'      region: "{record["Region"]}"')

        if "GeoLocation" in record:
            print(f'      geoLocation: {json.dumps(record["GeoLocation"])}')

    print(f"# Custom records exported: {custom_count}", file=sys.stderr)
    print(f"# AWS-managed records skipped: {len(records) - custom_count}", file=sys.stderr)

if __name__ == "__main__":
    main()
