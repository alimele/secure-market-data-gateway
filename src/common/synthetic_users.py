SYNTHETIC_USERS = {
    "retail-user": {
        "user_id": "usr_ext_retail_01",
        "display_name": "Retail User",
        "role": "RETAIL",
        "entitlement": [], # no realtime entitlement
    },
    "broker-user": {
        "user_id": "usr_ext_broker_01",
        "display_name": "Licensed Broker",
        "role": "BROKER",
        "entitlement": ["MARKET_DATA_REALTIME"],  # has it
    },
    "broker-no-entitlement": {
        "user_id": "usr_ext_broker_02",
        "display_name": "Unlicensed Broker",
        "role": "BROKER",
        "entitlements": [],  # broker role but no entitlement
    },
}


def get_synthetic_user(user_id: str):
    return SYNTHETIC_USERS.get(user_id)
