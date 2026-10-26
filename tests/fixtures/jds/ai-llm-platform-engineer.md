# Senior AI/LLM Platform Engineer

**Company:** Northwind Labs
**Location:** Remote (North America), with quarterly team offsites
**Team:** Inference Platform
**Employment type:** Full-time

## About Northwind Labs

Northwind Labs builds developer tooling that helps enterprise teams ship language-model-powered
products safely. Our customers run retrieval-augmented assistants, document pipelines and internal
agents on top of the platform we operate. We are a team of about 60 people and we run everything on
Kubernetes.

## The role

You will own the infrastructure that serves large language models to our customers and to our own
product teams. You will design, build and operate the inference stack, from GPU capacity planning
through to request-level observability, and you will work closely with ML engineers who ship new
models every few weeks.

## What you will do

- Design and run a multi-tenant LLM serving platform on Kubernetes using vLLM or a comparable engine.
- Build GPU scheduling and autoscaling policies that keep utilisation high without hurting latency.
- Operate retrieval-augmented generation (RAG) pipelines: embedding jobs, vector stores, indexing
  and re-indexing workflows, and the services that sit in front of them.
- Define and track service-level objectives for latency, throughput and cost per token.
- Instrument the platform end to end with metrics, traces and structured logs.
- Write Python tooling and services that make the platform self-service for ML engineers.
- Lead incident response for the inference platform and run blameless reviews afterwards.
- Review designs and mentor mid-level engineers on the team.

## Must-have qualifications

- 5+ years of experience in platform, infrastructure or site reliability engineering.
- Production experience with Kubernetes, including cluster operations, networking and upgrades.
- Strong Python skills; you write production services, not only scripts.
- Hands-on experience serving LLMs in production (vLLM, TGI, Triton or similar).
- Experience with GPU scheduling on Kubernetes (device plugins, node pools, bin packing, MIG or time slicing).
- Experience building or operating RAG pipelines.
- Solid observability practice with Prometheus, OpenTelemetry, Grafana or equivalent tooling.

## Nice-to-have qualifications

- Experience with the Model Context Protocol (MCP) or building MCP servers.
- Familiarity with agent frameworks such as LangGraph or similar orchestration libraries.
- Infrastructure as code with Terraform.
- Experience on AWS, particularly EKS, EC2 GPU instances and S3.
- Service mesh experience (Istio, Linkerd or Cilium service mesh).
- Contributions to open-source infrastructure or ML-serving projects.

## How we work

- Written design documents and asynchronous decision-making.
- On-call is shared across the team and limited to one week in six.
- We budget time every sprint for reliability and tooling work.

## Compensation and benefits

- Base salary range: USD 175,000 to 225,000, depending on experience and location.
- Equity, health coverage, a home-office stipend and a yearly learning budget.

## Hiring process

1. A 30-minute introductory conversation.
2. A technical conversation about a system you have operated.
3. A design exercise focused on inference platform trade-offs.
4. A final conversation with the engineering leadership team.

Northwind Labs is an equal opportunity employer. We welcome applicants from all backgrounds.
