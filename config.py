DEFAULT_CYCLE_TIMES = {
    "PRM4500-1": {  # XPERCO
        "Cuve Xperco DEC": {"heat": 33, "cool": 33, "deco": 16},
        "Cuve Xperco FILT": {"heat": 33, "cool": 33, "deco": 16},
        "Cuve Xperco NEW": {"heat": 35, "cool": 35, "deco": 35},
        "Bras Droit": {"heat": 24, "cool": 24, "deco": 25},
    },
    "PRM4500-2": {  # OXY
        "Cloison OXY": {"heat": 35, "cool": 45, "deco": 40},
        "Cuve OXY": {"heat": 45, "cool": 46, "deco": 60},
    },
}

DEFAULT_START_TIMES = {
    "Lundi": 6 * 60 + 25,
    "Autres jours": 4 * 60 + 52,
}

DEFAULT_END_TIME = 21 * 60 + 45
DEFAULT_LATENCE_MAX = 10
DEFAULT_SEND_GAP = 20
DEFAULT_DECO_GAP = 5

DEFAULT_FIRST_ARMS = {
    "PRM4500-1": 1,  # XPERCO
    "PRM4500-2": 4,  # OXY
}
