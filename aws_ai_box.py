#!/usr/bin/env python3
"""
AWS GPU AI Workstation Launcher with ComfyUI + ComfyUI-Manager
--------------------------------------------------------------
• Automatically creates and downloads a new EC2 key pair file (.pem)
• Lists GPU instance types (includes g6e.12xlarge, g6e.12xlargw)
• Queries AWS Pricing API for live on-demand rates
• Launches Deep Learning Base AMI (Ubuntu + CUDA)
• Installs ComfyUI and ComfyUI-Manager
• Waits for ComfyUI web UI and opens browser
• Clean destroy with `python aws_ai_box.py destroy`

Usage:
  python aws_ai_box.py create
  python aws_ai_box.py destroy
"""

import sys, os, time, platform, ipaddress, urllib.request, webbrowser, json, datetime
import boto3, requests
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------
DEFAULT_INSTANCE = "g6e.4xlarge"

INSTANCE_SPECS = {
    "g6.xlarge":     {"gpu": "NVIDIA L4",        "vcpus": 4,  "ram": "16 GB",   "vram": "24 GB"},
    "g6.8xlarge":    {"gpu": "NVIDIA L4",        "vcpus": 32, "ram": "128 GB",  "vram": "24 GB"},
    "g6.12xlarge":   {"gpu": "4×NVIDIA L4",      "vcpus": 48, "ram": "192 GB",  "vram": "96 GB"},
    "g6e.xlarge":    {"gpu": "NVIDIA L4",        "vcpus": 4,  "ram": "16 GB",   "vram": "24 GB"},
    "g6e.2xlarge":   {"gpu": "NVIDIA L4",        "vcpus": 8,  "ram": "32 GB",   "vram": "24 GB"},
    "g6e.4xlarge":   {"gpu": "NVIDIA L4",        "vcpus": 16, "ram": "64 GB",   "vram": "24 GB"},
    "g6e.12xlarge":  {"gpu": "3×NVIDIA L4",      "vcpus": 48, "ram": "192 GB",  "vram": "72 GB"},
    "g6e.12xlargw":  {"gpu": "3×NVIDIA L4 (W-Opt)","vcpus": 48,"ram": "192 GB", "vram": "72 GB"},
    "g6e.24xlarge":  {"gpu": "4×NVIDIA L4",      "vcpus": 96, "ram": "384 GB",  "vram": "96 GB"},
    "p5.4xlarge":    {"gpu": "NVIDIA H100",      "vcpus": 24, "ram": "96 GB",   "vram": "80 GB"},
}

FALLBACK_PRICES = {
    "g6.xlarge": 0.55, "g6.8xlarge": 2.30, "g6.12xlarge": 3.90,
    "g6e.xlarge": 0.65, "g6e.2xlarge": 1.10, "g6e.4xlarge": 2.00,
    "g6e.12xlarge": 6.00, "g6e.12xlargw": 6.10, "g6e.24xlarge": 8.50, "p5.4xlarge": 6.80,
}

PORTS = [22, 8188, 7860, 8888]
SECURITY_GROUP_NAME = "ai-g6e-box-sg"


REGION_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
}

# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------
def safe_aws_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (NoCredentialsError, EndpointConnectionError):
        sys.exit("AWS credentials invalid or network unreachable. Run `aws configure` or `aws sso login`.")
    except ClientError as e:
        sys.exit(f"AWS error: {e}")

def detect_public_ip():
    try:
        return urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5).read().decode().strip()
    except Exception:
        return None

def fetch_instance_price(region, instance_type):
    """Query AWS Pricing API for live on-demand pricing."""
    location = REGION_LOCATION.get(region)
    if not location:
        return None
    try:
        client = boto3.client("pricing", region_name="us-east-1")
        filters = [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
        ]
        resp = client.get_products(ServiceCode="AmazonEC2", Filters=filters, MaxResults=1)
        if not resp.get("PriceList"):
            return None
        data = json.loads(resp["PriceList"][0])
        terms = data.get("terms", {}).get("OnDemand", {})
        for term in terms.values():
            for dim in term.get("priceDimensions", {}).values():
                price = dim.get("pricePerUnit", {}).get("USD")
                if price:
                    return float(price)
    except Exception:
        return None
    return None

# ----------------------------------------------------------
# INPUT & KEYPAIR CREATION
# ----------------------------------------------------------
def prompt_user_inputs():
    print("=== AWS GPU AI Box Setup ===")
    region = input("AWS region (default us-east-1): ").strip() or "us-east-1"

    print("\nFetching live pricing...\n")
    instance_info = {}
    for itype, specs in INSTANCE_SPECS.items():
        price = fetch_instance_price(region, itype) or FALLBACK_PRICES.get(itype, 0)
        instance_info[itype] = {**specs, "price": price}

    print(f"{'Idx':<4}{'Type':<15}{'GPU':<20}{'vCPU':<6}{'RAM':<10}{'VRAM':<10}{'$/hr':<10}")
    print("-"*80)
    itypes = list(instance_info.keys())
    for i, itype in enumerate(itypes, 1):
        s = instance_info[itype]
        print(f"{i:<4}{itype:<15}{s['gpu']:<20}{s['vcpus']:<6}{s['ram']:<10}{s['vram']:<10}${s['price']:<10.4f}")
    print("-"*80)

    sel = input(f"Select instance [1-{len(itypes)}] (default {DEFAULT_INSTANCE}): ").strip()
    instance_type = itypes[int(sel)-1] if sel.isdigit() and 1 <= int(sel) <= len(itypes) else DEFAULT_INSTANCE

    print(f"\nSelected {instance_type}\n")

    ip_raw = input("Home IP (Enter to auto-detect): ").strip()
    if not ip_raw:
        auto = detect_public_ip()
        if not auto:
            sys.exit("Could not detect IP, please enter manually.")
        ip_raw = auto
        print(f"Detected public IP: {ip_raw}")
    try:
        home_ip = f"{ipaddress.ip_address(ip_raw)}/32"
    except ValueError:
        sys.exit(f"Invalid IP address: {ip_raw}")

    ec2 = boto3.client("ec2", region_name=region)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check for existing .pem files
    existing_pems = [f for f in os.listdir(script_dir) if f.startswith("ai_box_key_") and f.endswith(".pem")]
    key_name = None
    pem_path = None
    
    if existing_pems:
        print(f"\nFound existing key files:")
        for i, pem_file in enumerate(existing_pems, 1):
            print(f"  {i}. {pem_file}")
        
        # Check which keys exist on AWS
        try:
            aws_keys = safe_aws_call(ec2.describe_key_pairs)
            aws_key_names = {k['KeyName'] for k in aws_keys.get('KeyPairs', [])}
            
            valid_pems = []
            for pem_file in existing_pems:
                key_name_candidate = pem_file.replace(".pem", "")
                if key_name_candidate in aws_key_names:
                    valid_pems.append((pem_file, key_name_candidate))
            
            if valid_pems:
                print(f"\nFound {len(valid_pems)} key(s) that exist on AWS:")
                for i, (pem_file, key_name_candidate) in enumerate(valid_pems, 1):
                    print(f"  {i}. {key_name_candidate}")
                
                reuse = input(f"\nReuse existing key? (1-{len(valid_pems)}/n for new): ").strip().lower()
                if reuse and reuse != 'n':
                    try:
                        idx = int(reuse) - 1
                        if 0 <= idx < len(valid_pems):
                            pem_file, key_name = valid_pems[idx]
                            pem_path = os.path.join(script_dir, pem_file)
                            print(f"Reusing key: {key_name}")
                    except ValueError:
                        pass
        except Exception as e:
            print(f"Could not check AWS keys: {e}")
    
    # Create new key if not reusing
    if not key_name:
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        key_name = f"ai_box_key_{timestamp}"
        pem_path = os.path.join(script_dir, f"{key_name}.pem")
        
        print(f"\nCreating new key pair: {key_name}")
        new_key = safe_aws_call(ec2.create_key_pair, KeyName=key_name)
        try:
            with open(pem_path, "w") as f:
                f.write(new_key["KeyMaterial"])
            os.chmod(pem_path, 0o400)
            print(f"Key pair saved to: {pem_path}")
        except Exception as e:
            sys.exit(f"Failed to save key file: {e}")

    ami_override = input("Custom AMI ID (Enter for default Deep Learning Base): ").strip()
    return region, home_ip, key_name, ami_override, instance_type, pem_path

# ----------------------------------------------------------
# AWS RESOURCES
# ----------------------------------------------------------
def get_ec2(region): return boto3.client("ec2", region_name=region)
def get_ssm(region): return boto3.client("ssm", region_name=region)

def find_ami(ec2, ssm, region):
    """Find latest Deep Learning Base Ubuntu AMI with CUDA."""
    # Try SSM parameter store first (most reliable)
    try:
        param = ssm.get_parameter(Name="/aws/service/deep-learning-base/ami/ubuntu-22.04-cuda/latest")
        ami_id = param["Parameter"]["Value"]
        print(f"Found Deep Learning Base AMI: {ami_id}")
        return ami_id
    except Exception as e:
        print(f"SSM parameter lookup failed, searching for AMI by name...")
    
    # Fallback: Search for latest Deep Learning Base AMI
    try:
        response = ec2.describe_images(
            Owners=['amazon'],
            Filters=[
                {'Name': 'name', 'Values': ['Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*']},
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'architecture', 'Values': ['x86_64']},
            ]
        )
        
        if not response['Images']:
            print("No Deep Learning Base AMI found, trying Ubuntu 22.04...")
            # Last resort: Use standard Ubuntu 22.04
            response = ec2.describe_images(
                Owners=['099720109477'],  # Canonical
                Filters=[
                    {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
                    {'Name': 'state', 'Values': ['available']},
                ]
            )
        
        if not response['Images']:
            sys.exit("Could not find any suitable AMI. Please specify a custom AMI ID.")
        
        # Sort by creation date and get the latest
        latest_ami = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)[0]
        ami_id = latest_ami['ImageId']
        ami_name = latest_ami['Name']
        print(f"Found AMI: {ami_id} ({ami_name})")
        
        if 'Deep Learning' not in ami_name:
            print("Note: Using standard Ubuntu AMI. You may need to install NVIDIA drivers manually.")
        
        return ami_id
    except Exception as e:
        sys.exit(f"Failed to find AMI: {e}")

def find_vpc(ec2):
    vpcs = safe_aws_call(ec2.describe_vpcs).get("Vpcs", [])
    vpc_id = vpcs[0]["VpcId"] if vpcs else safe_aws_call(ec2.create_default_vpc)["Vpc"]["VpcId"]
    subnets = safe_aws_call(ec2.describe_subnets, Filters=[{"Name":"vpc-id","Values":[vpc_id]}]).get("Subnets",[])
    if not subnets:
        sys.exit("No subnets found.")
    return vpc_id, subnets[0]["SubnetId"]

def create_sg(ec2, vpc_id, home_ip):
    try:
        sg = ec2.create_security_group(GroupName=SECURITY_GROUP_NAME, Description="AI SG", VpcId=vpc_id)
        sg_id = sg["GroupId"]
    except ClientError as e:
        if "Duplicate" in str(e):
            sg_id = ec2.describe_security_groups(Filters=[{"Name":"group-name","Values":[SECURITY_GROUP_NAME]}])["SecurityGroups"][0]["GroupId"]
        else:
            raise
    rules = [{"IpProtocol":"tcp","FromPort":p,"ToPort":p,"IpRanges":[{"CidrIp":home_ip}]} for p in PORTS]
    try:
        ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=rules)
    except ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            print(f"Security group rules already exist (skipping)")
        else:
            sys.exit(f"AWS error: {e}")
    print(f"Security group ready: {sg_id}")
    return sg_id

# ----------------------------------------------------------
# EC2 LAUNCH & MONITOR
# ----------------------------------------------------------
def launch_instance(ec2, ami, key, sg, subnet, itype):
    print(f"Launching {itype} instance ...")
    user_data = """#!/bin/bash
set -euxo pipefail
apt-get update -y
apt-get install -y git python3-venv python3-pip tmux htop curl wget unzip
cd /opt/dlami/nvme
git clone https://github.com/comfyanonymous/ComfyUI.git || true
cd ComfyUI
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
cd custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git || true
cd ..
tmux new -d -s comfyui "cd /opt/dlami/nvme/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188"
"""
    resp = safe_aws_call(ec2.run_instances,
        ImageId=ami, InstanceType=itype, KeyName=key,
        MaxCount=1, MinCount=1,
        NetworkInterfaces=[{"SubnetId":subnet,"DeviceIndex":0,"AssociatePublicIpAddress":True,"Groups":[sg]}],
        TagSpecifications=[{"ResourceType":"instance","Tags":[{"Key":"Name","Value":"ai-g6e-box"}]}],
        UserData=user_data)
    return resp["Instances"][0]["InstanceId"]

def wait_for_ip(ec2, iid):
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[iid])
    for _ in range(30):
        ip = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0].get("PublicIpAddress")
        if ip:
            return ip
        time.sleep(5)
    sys.exit("No public IP found.")

def wait_for_comfyui(ip, timeout=600):
    url = f"http://{ip}:8188"
    print("Waiting for ComfyUI (~2–4 min)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(url, timeout=5).status_code == 200:
                print(f"\nComfyUI running at {url}")
                webbrowser.open(url)
                return
        except:
            pass
        print(".", end="", flush=True)
        time.sleep(10)
    print(f"\nTimeout. Check manually: {url}")

def destroy_resources(ec2):
    res = ec2.describe_instances(Filters=[{"Name":"tag:Name","Values":["ai-g6e-box"]}])
    ids = [i["InstanceId"] for r in res["Reservations"] for i in r["Instances"] if i["State"]["Name"] != "terminated"]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
        print(f"Terminated: {ids}")
    try:
        sg = ec2.describe_security_groups(Filters=[{"Name":"group-name","Values":[SECURITY_GROUP_NAME]}])["SecurityGroups"][0]["GroupId"]
        ec2.delete_security_group(GroupId=sg)
        print(f"Deleted SG {sg}")
    except:
        pass

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"create", "destroy"}:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    if action == "create":
        region, home_ip, key, ami_override, itype, pem_path = prompt_user_inputs()
        ec2, ssm = boto3.client("ec2", region_name=region), boto3.client("ssm", region_name=region)
        ami = ami_override or find_ami(ec2, ssm, region)
        vpc, sub = find_vpc(ec2)
        sg = create_sg(ec2, vpc, home_ip)
        iid = launch_instance(ec2, ami, key, sg, sub, itype)
        ip = wait_for_ip(ec2, iid)
        print(f"\nInstance ready @ {ip}. Installing ComfyUI...")
        print(f"SSH: ssh ubuntu@{ip} -i \"{pem_path}\"\n")
        wait_for_comfyui(ip)
        print("\nWhen finished, run: python aws_ai_box.py destroy")
    else:
        region = input("Region (default us-east-1): ").strip() or "us-east-1"
        destroy_resources(boto3.client("ec2", region_name=region))
        print("Teardown complete.")

if __name__ == "__main__":
    main()
