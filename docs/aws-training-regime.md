# AWS Training Regime: VMs, Instances & Networking

> **Goal:** Become confident creating and running EC2 instances and managing associated network connectivity in AWS, with a focus on hosting apps and services.
>
> **Assumed background:** Comfortable with Linux, command line, and general networking concepts (IP, DNS, firewalls).
>
> **Pace:** ~3–5 hours/week over 8–10 weeks.

---

## Before You Start

### Create an AWS Account

Sign up at [https://aws.amazon.com/free/](https://aws.amazon.com/free/) — the Free Tier gives you 12 months of limited but useful resources, including 750 hours/month of t3.micro EC2 time.

**Day-one security steps (do these before anything else):**

- [x] Enable MFA on your root account — go to IAM → Security credentials → MFA.
- [x] Create an IAM user with `AdministratorAccess` and use that for all day-to-day work. Never use the root account again except for billing/account emergencies.
- [x] Set a billing alarm: go to [CloudWatch → Alarms](https://console.aws.amazon.com/cloudwatch/home#alarmsV2:) and create one that triggers at $5 — this catches any accidental spend early.

---

## Phase 1 — Get Oriented (Week 1)

**Objective:** Understand the AWS landscape before touching any infrastructure.

**Concepts to cover:**

- AWS regions and availability zones (AZs) — what they are and why they matter for resilience
- The AWS Console and CLI — you'll use both
- IAM fundamentals: users, roles, policies, and the principle of least privilege
- The Free Tier — what's included and what will cost you

**Hands-on:**

- [ ] Navigate the AWS Console and locate EC2, VPC, IAM, and CloudWatch
- [ ] Install and configure the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html): run `aws configure` with your IAM user's access key
- [ ] Test your billing alarm using the CLI — this also validates that your CLI is configured correctly:
  ```bash
  aws cloudwatch set-alarm-state \
    --alarm-name "billing-alert-5usd" \
    --state-value ALARM \
    --state-reason "Testing alarm notification" \
    --region us-east-1
  ```
  Confirm the notification email arrives, then reset it:
  ```bash
  aws cloudwatch set-alarm-state \
    --alarm-name "billing-alert-5usd" \
    --state-value OK \
    --state-reason "Resetting after test" \
    --region us-east-1
  ```

**Resource:** [AWS Cloud Practitioner Essentials](https://explore.skillbuilder.aws/learn/courses/134/aws-cloud-practitioner-essentials) (free on AWS Skill Builder — sign up at [https://skillbuilder.aws](https://skillbuilder.aws)). The first few modules cover exactly this.

---

## Phase 2 — EC2: Your First Instances (Weeks 2–3)

**Objective:** Launch, configure, connect to, and manage EC2 instances (AWS's VM service).

**Concepts to cover:**

- Instance types and sizes — `t3.micro` is your free-tier friend
- AMIs (Amazon Machine Images) — the VM templates you launch from
- Key pairs — how SSH auth works in AWS (no password, only key-based)
- EBS volumes — the persistent block storage attached to your instances
- Instance lifecycle: pending → running → stopped → terminated

**Hands-on labs:**

- [ ] Launch a `t3.micro` Linux instance (Amazon Linux 2023 or Ubuntu 24.04 LTS)
- [ ] SSH into it using your downloaded key pair: `ssh -i your-key.pem ec2-user@<public-ip>`
- [ ] Install nginx (`sudo yum install nginx -y` or `sudo apt install nginx -y`), verify it serves HTTP
- [ ] Stop and start the instance — note that the public IP changes each time (this matters)
- [ ] Attach a second EBS volume, partition and format it (`mkfs.ext4`), mount it persistently via `/etc/fstab`
- [ ] Create an AMI from your running instance (Actions → Image and templates → Create image) — this is your reusable snapshot
- [ ] Terminate the instance and re-launch from your AMI to confirm it works

**Reference:** [EC2 Getting Started Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html)

---

## Phase 3 — Networking Deep Dive (Weeks 3–5)

**Objective:** Understand and build AWS networking from scratch. This is where most people struggle — your sysadmin background gives you a real advantage here.

**The mental model:**

| AWS Concept | Real-world equivalent |
|---|---|
| VPC | Your own private data center network |
| Subnet | A network segment (VLAN) |
| Internet Gateway | Your router's WAN uplink |
| NAT Gateway | A NAT/masquerade rule for private hosts |
| Security Group | Per-host iptables / stateful firewall |
| Network ACL | Per-subnet stateless ACL |
| Route Table | Static routing table |

**Concepts to cover:**

- VPC (Virtual Private Cloud) — your isolated network namespace in AWS
- Public vs. private subnets — the difference is purely routing
- Route tables — how traffic is directed within and out of your VPC
- Internet Gateway (IGW) — required for public subnets to reach the internet
- NAT Gateway — allows private instances to make outbound requests without being publicly reachable
- Security groups — stateful, attached per-instance, default-deny inbound
- Network ACLs — stateless, attached per-subnet, evaluated before security groups

**Hands-on labs:**

- [ ] **Build a custom VPC from scratch** (don't use the default — building your own is how you learn):
  - CIDR: `10.0.0.0/16`
  - Public subnet: `10.0.1.0/24` in AZ-a
  - Private subnet: `10.0.2.0/24` in AZ-a
  - Second public subnet: `10.0.3.0/24` in AZ-b (needed later for ALB)
  - Second private subnet: `10.0.4.0/24` in AZ-b

- [ ] **Wire up internet access:**
  - Create and attach an Internet Gateway to your VPC
  - In the public subnet's route table, add a route: `0.0.0.0/0 → IGW`
  - Confirm the private subnet's route table has no IGW route

- [ ] **Launch the bastion host pattern:**
  - EC2 instance in the public subnet — security group allows SSH (port 22) from your IP only
  - EC2 instance in the private subnet — security group allows SSH only from the public subnet's CIDR (`10.0.1.0/24`)
  - SSH to the public instance, then SSH from there to the private instance
  - Confirm the private instance cannot be reached directly from the internet

- [ ] **Add a NAT Gateway:**
  - Create a NAT Gateway in the public subnet (it needs an Elastic IP)
  - Add a route to the private subnet's route table: `0.0.0.0/0 → NAT Gateway`
  - From the private instance, run `curl https://example.com` — it should now succeed

**Reference:** [VPC Getting Started Guide](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-getting-started.html)

---

## Phase 4 — Elastic IPs, Load Balancers & DNS (Weeks 5–6)

**Objective:** Add stable addressing and traffic distribution to your setup.

**Concepts to cover:**

- Elastic IPs — static public IPv4 addresses that survive instance stop/start
- Application Load Balancer (ALB) — Layer 7 load balancer; distributes HTTP/HTTPS traffic across instances
- Target groups — the set of instances an ALB routes to, with health check configuration
- Route 53 — AWS's DNS service

**Hands-on labs:**

- [ ] Allocate an Elastic IP and associate it with your public instance — stop/start the instance and confirm the IP doesn't change
- [ ] Launch two EC2 instances in separate public subnets, both running nginx with different index.html content so you can tell them apart
- [ ] Create an Application Load Balancer:
  - Internet-facing, HTTP listener on port 80
  - Attach both public subnets
  - Create a target group pointing to both instances
  - Verify the ALB DNS name distributes requests across both
- [ ] If you have a domain: create a hosted zone in [Route 53](https://console.aws.amazon.com/route53/home) and add an A record (alias) pointing to your ALB. You can register a domain there too (~$12/yr for a `.com`).

---

## Phase 5 — Full Stack Deployment (Weeks 7–8)

**Objective:** Deploy a realistic multi-tier architecture.

This is the phase where everything comes together. The target architecture:

```
Internet
    │
    ▼
[ALB] — public subnets (AZ-a, AZ-b)
    │
    ▼
[App servers / EC2] — private subnets (AZ-a, AZ-b)
    │
    ▼
[RDS database] — private subnets (AZ-a, AZ-b)
```

**Security group rules:**

| Resource | Inbound allowed from | Port |
|---|---|---|
| ALB | `0.0.0.0/0` (internet) | 80, 443 |
| App servers | ALB security group | 8080 (or your app port) |
| RDS | App server security group | 5432 / 3306 |
| Bastion | Your IP only | 22 |
| App servers | Bastion security group | 22 |

**Hands-on labs:**

- [ ] Set up the VPC and subnets for the full architecture (public + private in two AZs)
- [ ] Launch app server EC2 instances in private subnets
- [ ] Provision an RDS instance (db.t3.micro) in private subnets
- [ ] Deploy a simple Flask or Node.js app that reads from the database
- [ ] Put the ALB in front of the app servers and confirm end-to-end traffic flow

**What to deploy:** A simple Python Flask or Node.js app that reads from the database and returns a response — even a basic "hello, this came from the DB" is enough to validate the full chain. Use [RDS Free Tier](https://aws.amazon.com/rds/free/) (db.t3.micro, 20GB) for the database.

---

## Phase 6 — Operational Basics (Weeks 9–10)

**Objective:** Learn to observe, access, and protect your running infrastructure.

**Hands-on labs:**

- [ ] **CloudWatch Logs & Metrics** — ship your app and system logs to CloudWatch; create dashboards for CPU, memory, and network. Set an alarm for CPU > 80%.
  - [CloudWatch Getting Started](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GettingStarted.html)

- [ ] **Systems Manager Session Manager** — SSH access to instances without opening port 22 at all. Attach the `AmazonSSMManagedInstanceCore` IAM policy to your instance profile and connect via the Console or `aws ssm start-session`. This is the modern best practice — no key management, full audit trail.
  - [Session Manager setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started.html)

- [ ] **EBS Snapshots** — create a snapshot of a running instance's volume as a point-in-time backup. Automate with AWS Backup or Data Lifecycle Manager.

- [ ] **AMI lifecycle** — get into the habit of creating a fresh AMI before any significant change. Easy rollback.

---

## Cost Management Tips

- **Tear things down when done.** The most common beginner mistake is leaving instances and NAT Gateways running. NAT Gateways cost ~$0.045/hr even when idle — that's ~$33/month.
- **Check your billing dashboard regularly:** [https://console.aws.amazon.com/billing/home](https://console.aws.amazon.com/billing/home)
- Instances in a *stopped* state don't incur compute charges, but their EBS volumes do (~$0.10/GB/month).
- Elastic IPs that are *not associated* with a running instance incur a small hourly charge — release them when not in use.

---

## Recommended Learning Resources

### AWS Skill Builder — Free, Official, Structured
**Sign up:** [https://skillbuilder.aws](https://skillbuilder.aws)

AWS's own learning platform. The free tier has plenty of material. The courses are short, modular, and well-produced. Recommended viewing order for this regime:

- [ ] [AWS Cloud Practitioner Essentials](https://explore.skillbuilder.aws/learn/courses/134/aws-cloud-practitioner-essentials) — start here. Modules 1–3 cover global infrastructure, IAM, and the console. Takes about 3–4 hours total but you can skip around.
- [ ] [Getting Started with Amazon EC2](https://explore.skillbuilder.aws/learn/courses/1611/getting-started-with-amazon-ec2) — short (~1hr), directly maps to Phase 2.
- [ ] [Amazon VPC Basics](https://explore.skillbuilder.aws/learn/courses/79/amazon-vpc-service-introduction) — covers subnets, route tables, IGW, security groups. Maps to Phase 3.
- [ ] [Architecting on AWS — Online Course Supplement](https://explore.skillbuilder.aws/learn/courses/8319/architecting-on-aws-online-course-supplement) — free companion to the paid classroom course; good reference for Phases 4 and 5.

---

### Stephane Maarek's AWS Solutions Architect Course — Udemy
**Link:** [AWS Certified Solutions Architect Associate SAA-C03](https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/)
**Cost:** ~$15 when on sale (Udemy runs sales constantly — never pay full price)

This is the most recommended paid resource in the AWS community, and it maps almost perfectly to this training regime. It's video-based, very hands-on, and Stephane explains the *why* behind everything rather than just clicking through the console. Relevant sections by phase:

| Phase | Sections to watch |
|---|---|
| Phase 1 | Section 3: IAM & AWS CLI |
| Phase 2 | Section 4: EC2 Fundamentals, Section 5: EC2 Storage |
| Phase 3 | Section 6: ELB & ASG (skip ASG for now), Section 14: VPC |
| Phase 4 | Section 6: ELB continued, Section 19: Route 53 |
| Phase 5 | Section 8: RDS, Section 14: VPC (revisit) |
| Phase 6 | Section 16: CloudWatch, Section 17: IAM Advanced |

The full course is ~27 hours — you don't need to watch it all. Treat it as a companion to the hands-on labs rather than something to binge before touching the console.

---

### AWS Documentation
**Link:** [https://docs.aws.amazon.com](https://docs.aws.amazon.com)

The official docs are genuinely good — clear, accurate, and regularly updated. The most useful pages for this regime:

- [EC2 User Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html) — comprehensive reference; use it when you hit something specific rather than reading cover to cover
- [VPC User Guide](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html) — the "How it works" and "Getting started" sections are worth reading fully before Phase 3
- [AWS CLI Command Reference](https://awscli.amazonaws.com/v2/documentation/api/latest/index.html) — searchable reference for every CLI command
- [AWS Architecture Center](https://aws.amazon.com/architecture/) — real-world reference architectures; useful when planning Phase 5

---

### AWS Workshop Studio — Free Hands-On Labs
**Link:** [https://workshops.aws](https://workshops.aws)

Free, guided, interactive labs that run in a real AWS environment. No account needed for many of them — AWS provisions a temporary account. Particularly good ones for this regime:

- [EC2 Spot and Savings Plans Workshop](https://workshops.aws/categories/EC2) — good Phase 2 supplement
- [Networking Immersion Day](https://catalog.workshops.aws/networking/en-US) — excellent deep dive for Phase 3; walks through building VPCs from scratch with diagrams
- [Well-Architected Labs](https://www.wellarchitectedlabs.com/) — practical labs around cost, reliability, and security; good after Phase 5

---

### freeCodeCamp AWS Course — YouTube
**Link:** [AWS Certified Cloud Practitioner Training (12 hours)](https://www.youtube.com/watch?v=SOTamWNgDKc)
**Cost:** Free

A solid free alternative to Skill Builder if you prefer video. Good for Phases 1–2. Watch at 1.5x speed.

---

### Quick Reference

| Resource | Best for | Cost |
|---|---|---|
| [AWS Skill Builder](https://skillbuilder.aws) | Structured official content, Phases 1–3 | Free |
| [Stephane Maarek (Udemy)](https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/) | Deep video walkthroughs, all phases | ~$15 |
| [AWS Workshops](https://workshops.aws) | Hands-on labs with guided steps | Free |
| [AWS Docs](https://docs.aws.amazon.com) | Reference while doing labs | Free |
| [freeCodeCamp YouTube](https://www.youtube.com/watch?v=SOTamWNgDKc) | Free video overview, Phases 1–2 | Free |
| [AWS Free Tier](https://aws.amazon.com/free/) | Account signup | Free |
| [AWS CLI install](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | CLI setup | Free |

---

## What's Next

Once you've completed this regime, the [AWS Solutions Architect Learning Plan (Includes Labs)](https://skillbuilder.aws/learning-plan/EB6SVX4CTK/aws-solutions-architect-learning-plan-includes-labs/SAJSTUCC44) on Skill Builder is a natural follow-on. It broadens your AWS knowledge into services this plan deliberately skips — S3, Lambda, API Gateway, DynamoDB, CloudFront, and KMS — and prepares you for the AWS Certified Solutions Architect Associate exam if that's a goal.

The EC2 and VPC labs in that plan also make good companions to Phases 2 and 3 of this regime: they provide guided, step-by-step lab environments that complement the freeform hands-on work here.

---

*Document maintained in `jim-thoughts` branch — last updated 2026-06-23.*
