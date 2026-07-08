# Developer Containment (Draft)

## Problem

Developer workstations present a broader risk profile than general-user workstations. Like all employees, developers have access to internal productivity and business systems: G-Drive, Gmail, Confluence, Jira, Bob, and similar.

But unlike general users, they also have VPN access to internal technical infrastructure across dev, QA, and production environments. A compromised developer workstation therefore gives an attacker two things simultaneously: access to the same soft internal resources available to any employee, and a live network tunnel into the technical estate.

This combination makes the developer workstation a high-value target. The attacker doesn't need to find and exploit a separate credential to reach internal systems — the VPN tunnel is already open, and the workstation is already trusted.

---

## Proposal

To reduce some exposure, we need developers to start using internal systems, rather than their workstations, for building, deploying, and testing their code.

The current practice of using their workstation as a hypervisor for VMs and/or containers exposes their workstation, and all of its access, to supply-chain exploits.

By having build, deploy, and testing run on internal systems, they will have the protection covered in the backend containment proposal.

This further reduces our exposure to supply-chain exploits.

---

## Context

Developers need a variety of ways to accomplish their tasks. This includes using tools on their workstation that interact with internal systems and shared resources such as GitHub.

Spinning up VMs and containers locally is done more out of expediency and simplicity than necessity.

More effort needs to be done to change their methods to use internal systems, which have greater protections than workstations.

---

## Approach

Provide developers with internal resources such as VMs, Nomad/k8s/Swarm hosting, and other things needed to develop, deploy, and test internally — as opposed to on their workstation.

Give the internal resources some type of ease of use, to encourage adoption.

Monitor developer workstations for current "hypervisor" activity, and encourage moving those activities to internal systems.

This is not a one-size-fits-all solution.

It is recognized that some development methods have a higher reliance on the workstation than others.

That being said, those development methods need to consider security over expediency.

---

## Expected Outcomes

Supply-chain exploits that target build and test tooling will hit internal systems rather than developer workstations. Those internal systems are subject to the egress controls described in the backend containment proposal, which significantly limits what a successful exploit can reach or exfiltrate.

The developer workstation becomes a lower-value target. It still has access to general internal resources, but it is no longer the place where code is built, containers are run, or deployments are triggered — removing the most attractive attack surface it currently presents.