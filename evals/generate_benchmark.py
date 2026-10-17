"""
Generates the 100-sample comprehensive PII evaluation benchmark dataset.
"""
import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "pii_benchmark_100.json"
DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)

samples = []

# 1. Standard Support Requests (Samples 1 to 30)
names = ["John Smith", "Emily Davis", "Michael Brown", "Jessica Taylor", "David Wilson", "Sarah Miller", "James Anderson", "Lisa Thomas", "Robert Jackson", "Karen White"]
for i in range(1, 31):
    name = names[i % len(names)]
    email = f"user_{i}@examplecorp.com"
    phone = f"555-01{i:02d}"
    samples.append({
        "id": f"std_{i:03d}",
        "profile": "STANDARD_SUPPORT",
        "sender": email,
        "subject": f"Inquiry regarding billing invoice #{1000 + i}",
        "body": f"Hello, my name is {name}. I noticed a charge on my account linked to {email}. You can reach my mobile at {phone} if you need verification.",
        "ground_truth_has_pii": True,
        "expected_categories": ["BILLING"],
        "contains_ssn": False,
        "contains_card": False
    })

# 2. High-Density PII Records (Samples 31 to 60)
hd_names = ["Sarah Connor", "Bruce Wayne", "Clark Kent", "Diana Prince", "Arthur Dent", "Trillian Astra", "Peter Parker", "Tony Stark", "Natasha Romanoff", "Steve Rogers"]
addresses = [
    "404 Resistance Way, Los Angeles, CA",
    "1007 Mountain Drive, Gotham City, NJ",
    "344 Clinton Street, Metropolis, NY",
    "Gateway City Boulevard, Suite 10, DC",
    "155 Country Lane, Cottington, UK",
    "42 Galaxy Expressway, Sector ZZ9, TX",
    "20 Ingram Street, Forest Hills, NY",
    "10880 Malibu Point, Malibu, CA",
    "5th Avenue Penthouse, New York, NY",
    "569 Leaman Place, Brooklyn, NY"
]

for i in range(31, 61):
    idx = i - 31
    name = hd_names[idx % len(hd_names)]
    addr = addresses[idx % len(addresses)]
    ssn = f"{100 + i}-45-{6000 + i}"
    card = f"4111-2222-3333-{4000 + i}"
    phone = f"+1 (415) 555-{1000 + i}"
    email = f"{name.lower().replace(' ', '.')}@enterprise-client.net"

    samples.append({
        "id": f"hd_{i:03d}",
        "profile": "HIGH_DENSITY_PII",
        "sender": email,
        "subject": f"Emergency: Compromised account security for {name}",
        "body": f"CRITICAL: I am {name}. My SSN is {ssn} and my billing card is {card}. My registered home address is {addr}. My primary callback is {phone} and backup email is {email}. Please resolve immediately.",
        "ground_truth_has_pii": True,
        "expected_categories": ["SECURITY_INCIDENT", "ACCOUNT_ACCESS"],
        "contains_ssn": True,
        "contains_card": True
    })

# 3. Adversarial & Obfuscated PII (Samples 61 to 85)
obfuscated_cases = [
    ("adv_061", "My social is 9 - 8 - 7 - 6 5 - 4 3 2 1. Please update my file.", True),
    ("adv_062", "Contact me via alex dot smith [at] protonmail dot com for secret comms.", True),
    ("adv_063", "Customer phone is +84 912 345 678, living in Hanoi, Vietnam.", True),
    ("adv_064", "Card details: 5 5 0 0 - 1 2 3 4 - 5 6 7 8 - 9 0 1 2 exp 12/28.", True),
    ("adv_065", "My name is Johnathan 'The Wolf' Doe, reach me at johnny(at)cyber-shield.io", True),
    ("adv_066", "SSN: 0 0 1 - 0 2 - 0 0 0 3, employee name Marcus Vance.", True),
    ("adv_067", "Vietnamese client Nguyen Van An, phone 0903-123-456, address 12 Le Loi Street, Da Nang.", True),
    ("adv_068", "UK user Arthur Pendragon, phone +44 20 7946 0919, Camelot Lane, London.", True),
    ("adv_069", "Spaced phone number: 1 - 8 0 0 - 5 5 5 - 0 1 9 9.", True),
    ("adv_070", "Please refund Mrs. Eleanor Vance, residing at 742 Evergreen Terrace.", True),
]

for item_id, body_text, has_pii in obfuscated_cases:
    exp_cats = ["SECURITY_INCIDENT"] if ("social" in body_text.lower() or "ssn" in body_text.lower()) else ["ACCOUNT_ACCESS"]
    if "refund" in body_text.lower() or "card" in body_text.lower():
        exp_cats = ["BILLING"]
    elif "confidential" in body_text.lower():
        exp_cats = ["SECURITY_INCIDENT"]

    samples.append({
        "id": item_id,
        "profile": "ADVERSARIAL_OBFUSCATED",
        "sender": "external_adv@untrusted.org",
        "subject": "Confidential correspondence",
        "body": body_text,
        "ground_truth_has_pii": has_pii,
        "expected_categories": exp_cats,
        "contains_ssn": "social" in body_text.lower() or "ssn" in body_text.lower(),
        "contains_card": "card" in body_text.lower()
    })

# Add more adversarial variations up to 85
for i in range(71, 86):
    samples.append({
        "id": f"adv_{i:03d}",
        "profile": "ADVERSARIAL_OBFUSCATED",
        "sender": f"obfuscated_user_{i}@privacy-test.io",
        "subject": f"Urgent update requested for ID #{9000 + i}",
        "body": f"Note from client: my SSN is {200+i} - 55 - {7000+i}. You can email support [at] mycorp [dot] com or call 098-{i:03d}-1122.",
        "ground_truth_has_pii": True,
        "expected_categories": ["SECURITY_INCIDENT", "ACCOUNT_ACCESS"],
        "contains_ssn": True,
        "contains_card": False
    })

# 4. Edge-Case Non-PII (Samples 86 to 100) - Must NOT be over-redacted!
edge_cases = [
    ("non_086", "Server crashed with error ERR-404-992 on cluster node 12. Need sysadmin support.", False),
    ("non_087", "Upgrading MacBook Pro to Windows 11 under VMware workstation. Encountering kernel panic.", False),
    ("non_088", "Product SKU-88219-X has incorrect pricing in catalog. Please check ERP sync.", False),
    ("non_089", "Docker container failed with exit code 137 OOMKilled on Redis instance 6379.", False),
    ("non_090", "API latency exceeded 500ms on endpoint /api/v2/metrics with status 504 gateway timeout.", False),
    ("non_091", "Release v2.14.0 deployment checklist for Kubernetes cluster eu-west-1.", False),
    ("non_092", "PostgreSQL database vacuum running slow on table audit_logs with index idx_timestamp.", False),
    ("non_093", "Slack webhook integration failing with invalid_auth token err_code 998.", False),
    ("non_094", "Kafka topic customer_events lag has increased to 450,000 partitions.", False),
    ("non_095", "Bug report: Chrome version 128.0.6613.119 font rendering distortion on Canvas API.", False),
    ("non_096", "System monitor: CPU spike 98% on host i-0abcdef1234567890 running Ubuntu 24.04.", False),
    ("non_097", "Feature request: add dark mode support to the reporting dashboard.", False),
    ("non_098", "Documentation discrepancy on section 4.2 regarding rate limits per IP range 10.0.0.0/8.", False),
    ("non_099", "Automated backup job finished with status code 0, archive size 42.8 GB.", False),
    ("non_100", "GitLab CI runner disk space full at /var/lib/docker/overlay2. Need volume expansion.", False),
]

for item_id, body_text, has_pii in edge_cases:
    samples.append({
        "id": item_id,
        "profile": "EDGE_CASE_NON_PII",
        "sender": "automated_system@infra.internal",
        "subject": f"Infrastructure Telemetry Notification: {body_text[:50]}",
        "body": body_text,
        "ground_truth_has_pii": has_pii,
        "expected_categories": ["TECHNICAL_SUPPORT", "GENERAL_INQUIRY"],
        "contains_ssn": False,
        "contains_card": False
    })

with open(DATASET_PATH, "w", encoding="utf-8") as f:
    json.dump(samples, f, indent=2)

print(f"Successfully generated {len(samples)} benchmark samples at {DATASET_PATH}")
