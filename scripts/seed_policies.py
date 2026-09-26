"""Seed resolution_policy with the four codes. Safe to re-run."""
import os

import psycopg

from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy

URL = os.environ.get(
    "DATABASE_URL", "postgresql://carbonx:carbonx@localhost:5432/carbonx"
).replace("postgresql+psycopg://", "postgresql://")

# RQ3 is unresolved, so no policy is the scheme's; VINTAGE_MATCHED is our default
# only because it is the one that never mixes years.
DEFAULT = Policy.VINTAGE_MATCHED

with psycopg.connect(URL) as conn:
    for policy, description in POLICY_DESCRIPTIONS.items():
        conn.execute(
            "INSERT INTO resolution_policy (code, description, is_default)"
            " VALUES (%s, %s, %s) ON CONFLICT (code) DO NOTHING",
            (policy.value, description, policy is DEFAULT),
        )
print(f"seeded {len(POLICY_DESCRIPTIONS)} resolution policies")
