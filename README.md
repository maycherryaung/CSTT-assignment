# CSTT-assignment
### Key Infrastructure Resources

| Resource | Detail |
|---|---|
| VPC `csttassg` | `10.0.0.0/16`, DNS support/hostnames enabled |
| Public Subnet A | `10.0.1.0/24` — Bastion Host |
| Public Subnet B | `10.0.2.0/24` |
| Private Subnet A | `10.0.3.0/24` — App Server |
| Private Subnet B | `10.0.4.0/24` |
| Internet Gateway | `cstt-assg-ig`, attached to VPC |
| NAT Gateway | `appservnatgate` in Public Subnet A (CloudFormation stack) — allows the private subnet to make outbound calls (e.g. `apt-get`) without being reachable from the internet |
| Bastion SG `bastionhostsg` | Inbound: SSH (22) from `195.133.135.250/32` only; unrestricted egress |
| App Server SG `appserversg` | Inbound: SSH (22) + HTTP (80) from `bastionhostsg` only; unrestricted egress |
| Public NACL | Inbound: SSH/HTTPS/HTTP/ephemeral; Outbound: SSH to VPC + ephemeral to internet |
| Private NACL | Inbound: SSH/HTTP from `10.0.1.0/24` + ephemeral from anywhere; Outbound: HTTPS/HTTP/ephemeral |

Infrastructure is defined in two CloudFormation templates:
- `basic_network_config.yaml` — initial stack (VPC, subnets, SGs, NACLs, IGW, route tables, no NAT)
- `network_config_cfn.yaml` — full stack (adds NAT Gateway, Elastic IP, cross-stack exports)

