from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class GlAccountCode(StrEnum):
    cleaning = "6100"
    building_maintenance = "6110"
    electrical = "6120"
    plumbing_hvac = "6130"
    equipment_tools = "6140"
    office_supplies = "6150"
    professional_fees = "6160"
    travel_transport = "6170"
    utilities = "6180"
    miscellaneous_opex = "6190"


class GlAccount(BaseModel):
    code: GlAccountCode
    name: str
    description: str


NORTHSTAR_GL_CATALOG: list[GlAccount] = [
    GlAccount(
        code=GlAccountCode.cleaning,
        name="Cleaning services",
        description="Janitorial, window cleaning, and waste disposal for Northstar facilities.",
    ),
    GlAccount(
        code=GlAccountCode.building_maintenance,
        name="Building maintenance",
        description="General repairs, handyman work, and routine facility upkeep.",
    ),
    GlAccount(
        code=GlAccountCode.electrical,
        name="Electrical services",
        description="Electrician work, lighting, and electrical repairs.",
    ),
    GlAccount(
        code=GlAccountCode.plumbing_hvac,
        name="Plumbing and HVAC",
        description="Plumbing, heating, ventilation, and air-conditioning services.",
    ),
    GlAccount(
        code=GlAccountCode.equipment_tools,
        name="Equipment and tools",
        description="Tool rental, small equipment purchases, and safety gear.",
    ),
    GlAccount(
        code=GlAccountCode.office_supplies,
        name="Office supplies",
        description="Stationery, printer supplies, and other office consumables.",
    ),
    GlAccount(
        code=GlAccountCode.professional_fees,
        name="Professional fees",
        description="Legal, accounting, consulting, and other professional services.",
    ),
    GlAccount(
        code=GlAccountCode.travel_transport,
        name="Travel and transport",
        description="Fuel, parking, mileage, and public transport for facility operations.",
    ),
    GlAccount(
        code=GlAccountCode.utilities,
        name="Utilities",
        description="Electricity, water, gas, and other utility costs for facilities.",
    ),
    GlAccount(
        code=GlAccountCode.miscellaneous_opex,
        name="Miscellaneous operating expenses",
        description="Other operating expenses not covered by the accounts above.",
    ),
]

_GL_ACCOUNT_BY_CODE = {account.code: account for account in NORTHSTAR_GL_CATALOG}
_GL_ACCOUNT_BY_CODE_VALUE = {account.code.value: account for account in NORTHSTAR_GL_CATALOG}


def format_catalog_for_prompt() -> str:
    lines = ["Northstar GL catalog (choose exactly one code):"]
    for account in NORTHSTAR_GL_CATALOG:
        lines.append(f"- {account.code.value}: {account.name} — {account.description}")
    return "\n".join(lines)


def get_gl_account(code: GlAccountCode | str) -> GlAccount | None:
    if isinstance(code, GlAccountCode):
        return _GL_ACCOUNT_BY_CODE.get(code)
    return _GL_ACCOUNT_BY_CODE_VALUE.get(code)
