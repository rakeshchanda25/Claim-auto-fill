FIELD_LEVEL = "field-level"
PAGE_LEVEL = "page-level"
FORM_ONLY = "form-identified"
UNSOURCED = "unsourced"

ARCHETYPES = ("boxed", "ruled", "compact")

STATE_FORMS = {
    "AL": ("AST-27", "Alabama Department of Public Safety", "Alabama Uniform Traffic Crash Report", FORM_ONLY, "boxed"),
    "AK": ("Form 12-200", "Alaska Department of Transportation", "Alaska Traffic Collision Report", FORM_ONLY, "ruled"),
    "AZ": ("Form 01-2704", "Arizona Department of Public Safety", "Arizona Traffic Crash Report", FORM_ONLY, "boxed"),
    "AR": ("Form 5-2000", "Arkansas State Police", "Arkansas Motor Vehicle Crash Report", FORM_ONLY, "compact"),
    "CA": ("CHP 555", "California Highway Patrol", "Traffic Collision Report", PAGE_LEVEL, "ruled"),
    "CO": ("DR 2447", "Colorado State Patrol", "Colorado Traffic Accident Report", FORM_ONLY, "boxed"),
    "CT": ("PR-1", "Connecticut Department of Transportation", "Connecticut Uniform Police Crash Report", FORM_ONLY, "ruled"),
    "DE": ("Form 438", "Delaware State Police", "Delaware Uniform Collision Report", FORM_ONLY, "compact"),
    "FL": ("HSMV 90003", "Florida Department of Highway Safety and Motor Vehicles", "Florida Traffic Crash Report", FORM_ONLY, "boxed"),
    "GA": ("GDOT-523", "Georgia Department of Transportation", "Georgia Motor Vehicle Crash Report", FORM_ONLY, "ruled"),
    "HI": (None, "Hawaii Department of Transportation", "Hawaii Motor Vehicle Crash Report", UNSOURCED, "compact"),
    "ID": ("IDT-90", "Idaho Transportation Department", "Idaho Vehicle Collision Report", FORM_ONLY, "boxed"),
    "IL": ("SR 1050", "Illinois Department of Transportation", "Illinois Traffic Crash Report", FORM_ONLY, "ruled"),
    "IN": ("Form 23558", "Indiana State Police", "Indiana Officer's Standard Crash Report", FORM_ONLY, "compact"),
    "IA": (None, "Iowa Department of Transportation", "Iowa Investigating Officer's Crash Report", UNSOURCED, "boxed"),
    "KS": ("Form 852", "Kansas Department of Transportation", "Kansas Motor Vehicle Accident Report", FORM_ONLY, "ruled"),
    "KY": ("KSP-74", "Kentucky State Police", "Kentucky Uniform Police Traffic Collision Report", FORM_ONLY, "compact"),
    "LA": ("DPSSP 3105", "Louisiana State Police", "Louisiana Uniform Motor Vehicle Traffic Crash Report", FORM_ONLY, "boxed"),
    "ME": (None, "Maine State Police", "Maine Uniform Crash Report", UNSOURCED, "ruled"),
    "MD": ("MSP-1", "Maryland State Police", "Maryland Motor Vehicle Crash Report", FORM_ONLY, "compact"),
    "MA": ("CRA-65", "Massachusetts Registry of Motor Vehicles", "Massachusetts Motor Vehicle Crash Operator Report", FORM_ONLY, "boxed"),
    "MI": ("UD-10", "Michigan State Police", "Michigan Traffic Crash Report", FORM_ONLY, "ruled"),
    "MN": ("PS32003", "Minnesota Department of Public Safety", "Minnesota Motor Vehicle Crash Report", FORM_ONLY, "compact"),
    "MS": (None, "Mississippi Department of Public Safety", "Mississippi Uniform Crash Report", UNSOURCED, "boxed"),
    "MO": ("SHP-2P", "Missouri State Highway Patrol", "Missouri Uniform Crash Report", FORM_ONLY, "ruled"),
    "MT": (None, "Montana Highway Patrol", "Montana Vehicle Crash Report", UNSOURCED, "compact"),
    "NE": ("Form 40", "Nebraska Department of Transportation", "Nebraska Investigator's Motor Vehicle Crash Report", FORM_ONLY, "boxed"),
    "NV": (None, "Nevada Department of Public Safety", "Nevada Traffic Crash Report", UNSOURCED, "ruled"),
    "NH": ("DSMV 159", "New Hampshire Division of Motor Vehicles", "New Hampshire Uniform Police Traffic Accident Report", FORM_ONLY, "compact"),
    "NJ": ("NJTR-1", "New Jersey Department of Transportation", "New Jersey Police Crash Investigation Report", FORM_ONLY, "boxed"),
    "NM": ("SH10074", "New Mexico Department of Transportation", "New Mexico Uniform Crash Report", FORM_ONLY, "ruled"),
    "NY": ("MV-104A", "New York State Department of Motor Vehicles", "Police Accident Report", FORM_ONLY, "compact"),
    "NC": ("DMV-349", "North Carolina Division of Motor Vehicles", "North Carolina Crash Report", FORM_ONLY, "boxed"),
    "ND": ("SFN 2355", "North Dakota Department of Transportation", "North Dakota Crash Report", FORM_ONLY, "ruled"),
    "OH": ("OH-1", "Ohio Department of Public Safety", "Ohio Traffic Crash Report", FORM_ONLY, "compact"),
    "OK": ("DPS 0192-1", "Oklahoma Department of Public Safety", "Oklahoma Official Traffic Collision Report", FORM_ONLY, "boxed"),
    "OR": ("Form 73546-A", "Oregon Department of Transportation", "Oregon Police Traffic Crash Report", FORM_ONLY, "ruled"),
    "PA": (None, "Pennsylvania State Police", "Pennsylvania Police Crash Reporting Form", UNSOURCED, "compact"),
    "RI": ("DMVSAF", "Rhode Island Division of Motor Vehicles", "Rhode Island Uniform Crash Report", FORM_ONLY, "boxed"),
    "SC": ("TR-310", "South Carolina Department of Public Safety", "South Carolina Traffic Collision Report", FORM_ONLY, "ruled"),
    "SD": (None, "South Dakota Highway Patrol", "South Dakota Motor Vehicle Traffic Accident Report", UNSOURCED, "compact"),
    "TN": ("SF-1203", "Tennessee Department of Safety", "Tennessee Uniform Crash Report", FORM_ONLY, "boxed"),
    "TX": ("CR-3", "Texas Department of Transportation", "Texas Peace Officer's Crash Report", FIELD_LEVEL, "boxed"),
    "UT": ("DI-9", "Utah Department of Public Safety", "Utah Traffic Collision Report", FORM_ONLY, "ruled"),
    "VT": (None, "Vermont Department of Motor Vehicles", "Vermont Uniform Crash Report", UNSOURCED, "compact"),
    "VA": (None, "Virginia Department of Motor Vehicles", "Virginia Police Crash Report", UNSOURCED, "boxed"),
    "WA": ("Form 30034513", "Washington State Patrol", "Washington Police Traffic Collision Report", FORM_ONLY, "ruled"),
    "WV": ("DMV-17F", "West Virginia Division of Motor Vehicles", "West Virginia Uniform Traffic Crash Report", FORM_ONLY, "compact"),
    "WI": ("MV4000", "Wisconsin Department of Transportation", "Wisconsin Motor Vehicle Crash Report", FORM_ONLY, "boxed"),
    "WY": ("PR-902", "Wyoming Department of Transportation", "Wyoming Investigator's Traffic Crash Report", FORM_ONLY, "ruled"),
}


def state_form(code):
    if not code:
        return None
    entry = STATE_FORMS.get(str(code).upper())
    if not entry:
        return None
    form_number, agency, title, fidelity, archetype = entry
    return {
        "code": str(code).upper(),
        "form_number": form_number,
        "agency": agency,
        "title": title,
        "fidelity": fidelity,
        "archetype": archetype,
    }


def sourced_states():
    return sorted(c for c, e in STATE_FORMS.items() if e[3] != UNSOURCED)
