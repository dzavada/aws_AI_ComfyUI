# AWS GPU AI Workstation Launcher

Automated AWS EC2 GPU instance launcher with ComfyUI and ComfyUI-Manager pre-installed. Launch powerful GPU workstations in minutes with automatic setup, live pricing, and one-command teardown.

## Features

- **One-Command Launch** - Fully automated EC2 instance creation and setup
- **Live Pricing** - Real-time AWS pricing via Pricing API
- **Automatic Key Management** - Creates and saves SSH key pairs automatically
- **Pre-installed Software** - ComfyUI + ComfyUI-Manager ready to use
- **Auto Browser Launch** - Opens ComfyUI web UI when ready
- **Security** - Automatic security group configuration with your IP
- **Easy Cleanup** - One command to destroy all resources
- **Multiple GPU Options** - Support for g6, g6e, and p5 instance types

## Prerequisites

- Python 3.7+
- AWS Account with appropriate permissions
- AWS CLI configured (`aws configure` or `aws sso login`)
- Required Python packages:
  ```bash
  pip install boto3 requests
  ```

## Quick Start

### 1. Setup AWS Credentials

```bash
aws configure
# OR
aws sso login
```

### 2. Launch Instance

```bash
python main.py create
```

Follow the interactive prompts to:
- Select AWS region (default: us-east-1)
- Choose instance type from the pricing table
- Confirm your public IP (auto-detected)
- Optionally specify a custom AMI

### 3. Access Your Workstation

Once launched, the script will:
- Display SSH connection command
- Wait for ComfyUI to be ready
- Automatically open the web UI in your browser

### 4. Destroy Resources

When finished:

```bash
python main.py destroy
```

This terminates the instance and cleans up security groups.

## Available Instance Types

| Instance Type | GPU | vCPUs | RAM | VRAM | Est. Cost/hr |
|--------------|-----|-------|-----|------|-------------|
| g6.xlarge | NVIDIA L4 | 4 | 16 GB | 24 GB | ~$0.55 |
| g6.8xlarge | NVIDIA L4 | 32 | 128 GB | 24 GB | ~$2.30 |
| g6.12xlarge | 4×NVIDIA L4 | 48 | 192 GB | 96 GB | ~$3.90 |
| g6e.xlarge | NVIDIA L4 | 4 | 16 GB | 24 GB | ~$0.65 |
| g6e.2xlarge | NVIDIA L4 | 8 | 32 GB | 24 GB | ~$1.10 |
| g6e.4xlarge | NVIDIA L4 | 16 | 64 GB | 24 GB | ~$2.00 |
| g6e.12xlarge | 3×NVIDIA L4 | 48 | 192 GB | 72 GB | ~$6.00 |
| g6e.12xlargw | 3×NVIDIA L4 (W-Opt) | 48 | 192 GB | 72 GB | ~$6.10 |
| g6e.24xlarge | 4×NVIDIA L4 | 96 | 384 GB | 96 GB | ~$8.50 |
| p5.4xlarge | NVIDIA H100 | 24 | 96 GB | 80 GB | ~$6.80 |

*Prices are estimates and vary by region. Live pricing is shown when running the script.*

## Configuration

### Default Settings

- **Default Instance**: `g6e.4xlarge`
- **Default Region**: `us-east-1`
- **Security Group**: `ai-g6e-box-sg`
- **Open Ports**: 22 (SSH), 8188 (ComfyUI), 7860 (Gradio), 8888 (Jupyter)

### AMI Selection

The script automatically finds the latest Deep Learning Base AMI with CUDA support. If unavailable, it falls back to:
1. Latest Deep Learning Base AMI by name search
2. Latest Ubuntu 22.04 AMI (requires manual NVIDIA driver installation)

You can also specify a custom AMI ID when prompted.

## SSH Access

After launch, connect via SSH:

```bash
ssh ubuntu@<PUBLIC_IP> -i ai_box_key_<timestamp>.pem
```

The key file is automatically saved in the same directory as the script.

## Pre-installed Software

The instance comes with:
- **ComfyUI** - Web-based Stable Diffusion UI
- **ComfyUI-Manager** - Plugin manager for ComfyUI
- **PyTorch** with CUDA 12.1 support
- **Python 3** with venv
- **tmux** - ComfyUI runs in a persistent tmux session
- **Development tools** - git, curl, wget, etc.

### Accessing ComfyUI

- **Web UI**: `http://<PUBLIC_IP>:8188`
- **tmux session**: `tmux attach -t comfyui`

## Troubleshooting

### "InvalidPermission.Duplicate" Error
 **Fixed**: The script now handles duplicate security group rules gracefully.

### "InvalidAMIID.NotFound" Error
 **Fixed**: The script now dynamically finds the latest available AMI in your region.

### ComfyUI Not Loading
- Check instance is running: `python main.py status` (if implemented)
- SSH into instance and check logs: `tmux attach -t comfyui`
- Verify security group allows your IP on port 8188

### Cannot Connect via SSH
- Ensure your IP hasn't changed since launch
- Check the key file permissions: `chmod 400 ai_box_key_*.pem`
- Verify security group rules in AWS console

## Cost Management

 **Important**: GPU instances are expensive!

- g6e.xlarge: ~$0.65/hour = ~$468/month if left running
- g6e.4xlarge: ~$2.00/hour = ~$1,440/month if left running
- p5.4xlarge: ~$6.80/hour = ~$4,896/month if left running

**Always remember to destroy your instance when done:**
```bash
python main.py destroy
```

Set up billing alerts in AWS to avoid unexpected charges.

## Security Notes

- The script only allows SSH/HTTP access from your public IP
- SSH keys are created with 400 permissions
- Security groups are cleaned up on destroy
- All resources are tagged for easy identification

## Supported Regions

- us-east-1 (N. Virginia)
- us-east-2 (Ohio)
- us-west-1 (N. California)
- us-west-2 (Oregon)

Additional regions can be added by updating the `REGION_LOCATION` dictionary.

## Architecture

```
┌─────────────────┐
│   Your Machine  │
│  (Run Script)   │
└────────┬────────┘
         │
         ├─ Create Key Pair
         ├─ Setup Security Group
         ├─ Launch EC2 Instance
         │  └─ Deep Learning Base AMI
         │     └─ Auto-install ComfyUI
         │
         └─ Wait & Open Browser
              ↓
    ┌──────────────────┐
    │  EC2 GPU Instance │
    │  - NVIDIA Drivers │
    │  - CUDA 12.1      │
    │  - ComfyUI:8188   │
    └──────────────────┘
```

## Development

### Project Structure
```
.
├── main.py                  # Main launcher script
├── README.md               # This file
└── ai_box_key_*.pem       # Generated SSH keys (git ignored)
```

### Future Enhancements
- [ ] Instance status command
- [ ] Support for more regions
- [ ] Spot instance support
- [ ] Custom user data scripts
- [ ] Multiple simultaneous instances
- [ ] Web dashboard

## License

This project is provided as-is for educational and development purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This tool creates AWS resources that incur costs. Users are responsible for:
- Monitoring and managing AWS costs
- Securing their instances and data
- Complying with AWS terms of service
- Following security best practices

**Remember to destroy instances when not in use to avoid unnecessary charges!**

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review AWS CloudWatch logs
3. Check AWS EC2 console for instance status
4. Open an issue on GitHub

---

**Happy GPU Computing! **
