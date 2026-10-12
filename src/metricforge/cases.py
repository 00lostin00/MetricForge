import json
import random
from pathlib import Path

from .models import Case, FinancialRow

DATA_VERSION = "metricforge-fictional-v1"


def load_cases(root: Path) -> list[Case]:
    return [
        Case.model_validate(item)
        for item in json.loads((root / "fixtures/cases.json").read_text(encoding="utf-8"))
    ]


def generated_cases(seed: int, count: int) -> list[Case]:
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        current_values = [str(rng.randint(-20, 2000)) for _ in range(3)]
        previous_values = [str(rng.randint(-20, 2000)) for _ in range(3)]
        row = FinancialRow(
            company=f"GENERATED_{index}",
            year=2025,
            unit=rng.choice(["CNY", "CNY_10K"]),
            revenue=current_values[0],
            net_profit=current_values[1],
            operating_cashflow=current_values[2],
            source=f"generated:{seed}:{index}:2025",
        )
        previous = FinancialRow(
            company=row.company,
            year=2024,
            unit=rng.choice(["CNY", "CNY_10K"]),
            revenue=previous_values[0],
            net_profit=previous_values[1],
            operating_cashflow=previous_values[2],
            source=f"generated:{seed}:{index}:2024",
        )
        mode = index % 8
        if mode == 1:
            previous = None
        elif mode == 2:
            row.net_profit = None
        elif mode == 3:
            previous.revenue = "0"
        elif mode == 4:
            row.scope = "parent"
        elif mode == 5:
            previous.year = 2023
        elif mode == 6:
            row.revenue = "0"
        cases.append(
            Case(id=f"seed-{seed}-{index}", current=row, previous=previous, origin="generated")
        )
    return cases
