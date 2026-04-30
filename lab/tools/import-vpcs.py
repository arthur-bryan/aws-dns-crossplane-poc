#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_DIR = REPO_ROOT / "entities" / "catalog" / "aws-vpcs"


def aws(*args: str) -> dict | list:
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR running `aws {' '.join(args)}`:\n{result.stderr}")
    return json.loads(result.stdout or "{}")


def list_regions() -> list[str]:
    data = aws("ec2", "describe-regions", "--query", "Regions[].RegionName")
    return data or []


def list_vpcs(region: str) -> list[dict]:
    data = aws("ec2", "describe-vpcs", "--region", region, "--query", "Vpcs")
    return data or []


def vpc_name(vpc: dict) -> str:
    for tag in vpc.get("Tags", []) or []:
        if tag.get("Key") == "Name" and tag.get("Value"):
            return tag["Value"]
    return ""


def vpc_yaml(vpc: dict, region: str) -> str:
    vpc_id = vpc["VpcId"]
    cidr = vpc.get("CidrBlock", "")
    is_default = bool(vpc.get("IsDefault", False))
    name = vpc_name(vpc)
    title = f"{vpc_id} ({region})" + (f" — {name}" if name else "")
    description = f"VPC {vpc_id} in {region}"
    if cidr:
        description += f", CIDR {cidr}"
    if is_default:
        description += ", default"
    tags = ["aws", "vpc", region]
    if is_default:
        tags.append("default")
    tag_lines = "\n".join(f"    - {t}" for t in tags)
    name_annotation = f"\n            dock.tech/vpc-name: {name}" if name else ""
    return dedent(f"""\
        ---
        apiVersion: backstage.io/v1alpha1
        kind: Resource
        metadata:
          name: vpc-{vpc_id}
          title: {title}
          description: "{description}"
          annotations:
            dock.tech/vpc-id: {vpc_id}
            dock.tech/vpc-region: {region}
            dock.tech/vpc-cidr: {cidr}
            dock.tech/vpc-is-default: "{str(is_default).lower()}"{name_annotation}
          tags:
        {tag_lines}
          links:
            - title: View in AWS Console
              url: https://console.aws.amazon.com/vpc/home?region={region}#VpcDetails:VpcId={vpc_id}
              icon: cloud
        spec:
          type: aws-vpc
          owner: group:default/infrastructure
        """)


class Writer:
    def __init__(self, write: bool):
        self.write = write
        self.created = 0
        self.skipped = 0

    def handle(self, path: Path, content: str, label: str) -> None:
        if path.exists():
            existing = path.read_text()
            if existing == content:
                print(f"  skip   {label} (unchanged)  {path.relative_to(REPO_ROOT)}")
                self.skipped += 1
                return
        if not self.write:
            print(f"  DRY    {label}                {path.relative_to(REPO_ROOT)}")
            self.created += 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"  WRITE  {label}                {path.relative_to(REPO_ROOT)}")
        self.created += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--regions", nargs="+", help="restrict to these AWS regions")
    args = ap.parse_args()

    regions = args.regions or list_regions()
    if not regions:
        print("no regions discovered", file=sys.stderr)
        return 2

    print(f"scanning {len(regions)} region(s) for VPCs")
    print(f"target: {CATALOG_DIR.relative_to(REPO_ROOT)}/")
    print()

    writer = Writer(write=args.write)
    total_vpcs = 0
    for region in regions:
        vpcs = list_vpcs(region)
        if not vpcs:
            continue
        print(f"=== {region}: {len(vpcs)} VPC(s) ===")
        for vpc in vpcs:
            content = vpc_yaml(vpc, region)
            path = CATALOG_DIR / f"{vpc['VpcId']}.yaml"
            writer.handle(path, content, f"vpc {vpc['VpcId']}")
            total_vpcs += 1

    print()
    print(f"summary: {total_vpcs} VPCs, {writer.created} created, {writer.skipped} unchanged")
    if not args.write and writer.created:
        print("re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
