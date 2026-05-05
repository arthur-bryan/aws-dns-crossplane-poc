#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_DIR = REPO_ROOT / "entities" / "catalog" / "aws-vpcs"

LAB_ACCOUNTS = [
    {"name": "prd-account", "id": "597230762851", "assumeRole": None},
    {
        "name": "dev-account",
        "id": "309670275661",
        "assumeRole": "arn:aws:iam::309670275661:role/OrganizationAccountAccessRole",
    },
]

def run_aws(args: list[str], env: dict[str, str]) -> dict | list:
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        capture_output=True, text=True, check=False, env=env,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR running `aws {' '.join(args)}`:\n{result.stderr}")
    return json.loads(result.stdout or "{}")

def base_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    return env

def assume_role(env: dict[str, str], role_arn: str, session: str) -> dict[str, str]:
    out = run_aws(
        ["sts", "assume-role", "--role-arn", role_arn, "--role-session-name", session],
        env=env,
    )
    creds = out["Credentials"]
    new_env = dict(env)
    new_env.update({
        "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
        "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
        "AWS_SESSION_TOKEN": creds["SessionToken"],
    })
    return new_env

def list_regions(env: dict[str, str]) -> list[str]:
    return run_aws(["ec2", "describe-regions", "--query", "Regions[].RegionName"], env=env) or []

def list_vpcs(region: str, env: dict[str, str]) -> list[dict]:
    return run_aws(["ec2", "describe-vpcs", "--region", region, "--query", "Vpcs"], env=env) or []

def vpc_name(vpc: dict) -> str:
    for tag in vpc.get("Tags", []) or []:
        if tag.get("Key") == "Name" and tag.get("Value"):
            return tag["Value"]
    return ""

def vpc_yaml(vpc: dict, region: str, account: dict) -> str:
    vpc_id = vpc["VpcId"]
    cidr = vpc.get("CidrBlock", "")
    is_default = bool(vpc.get("IsDefault", False))
    name = vpc_name(vpc)
    title = f"{vpc_id} ({region}, {account['name']})" + (f" — {name}" if name else "")
    description = f"VPC {vpc_id} in {region} ({account['name']})"
    if cidr:
        description += f", CIDR {cidr}"
    if is_default:
        description += ", default"
    tags = ["aws", "vpc", region, account["name"]]
    if is_default:
        tags.append("default")

    lines = [
        "---",
        "apiVersion: backstage.io/v1alpha1",
        "kind: Resource",
        "metadata:",
        f"  name: {vpc_id}",
        f"  title: {title}",
        f'  description: "{description}"',
        "  annotations:",
        f"    dock.tech/vpc-id: {vpc_id}",
        f"    dock.tech/vpc-region: {region}",
        f"    dock.tech/vpc-cidr: {cidr}",
        f'    dock.tech/vpc-is-default: "{str(is_default).lower()}"',
        f"    dock.tech/aws-account-id: \"{account['id']}\"",
        f"    dock.tech/aws-account-name: {account['name']}",
    ]
    if name:
        lines.append(f"    dock.tech/vpc-name: {name}")
    lines.append("  tags:")
    lines.extend(f"    - {t}" for t in tags)
    spec_type = "aws-vpc-default" if is_default else "aws-vpc"
    lines.extend([
        "  links:",
        "    - title: View in AWS Console",
        f"      url: https://console.aws.amazon.com/vpc/home?region={region}#VpcDetails:VpcId={vpc_id}",
        "      icon: cloud",
        "spec:",
        f"  type: {spec_type}",
        "  owner: group:default/infrastructure",
        "",
    ])
    return "\n".join(lines)

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
    ap.add_argument("--accounts", nargs="+", help="restrict to these account names")
    args = ap.parse_args()

    accounts = LAB_ACCOUNTS
    if args.accounts:
        wanted = set(args.accounts)
        accounts = [a for a in LAB_ACCOUNTS if a["name"] in wanted]
        if not accounts:
            print(f"no matching accounts in {[a['name'] for a in LAB_ACCOUNTS]}", file=sys.stderr)
            return 2

    print(f"target: {CATALOG_DIR.relative_to(REPO_ROOT)}/")
    print()

    writer = Writer(write=args.write)
    total_vpcs = 0

    for account in accounts:
        env = base_env()
        if account["assumeRole"]:
            env = assume_role(env, account["assumeRole"], "import-vpcs")
        regions = args.regions or list_regions(env)
        print(f"=== account {account['name']} ({account['id']}): scanning {len(regions)} region(s) ===")
        for region in regions:
            vpcs = list_vpcs(region, env)
            if not vpcs:
                continue
            print(f"  {region}: {len(vpcs)} VPC(s)")
            for vpc in vpcs:
                content = vpc_yaml(vpc, region, account)
                path = CATALOG_DIR / f"{vpc['VpcId']}.yaml"
                writer.handle(path, content, f"vpc {vpc['VpcId']}")
                total_vpcs += 1
        print()

    print(f"summary: {total_vpcs} VPCs scanned, {writer.created} written, {writer.skipped} unchanged")
    if not args.write and writer.created:
        print("re-run with --write to apply.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
