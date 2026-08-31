SYNTHETIC_USERS = {
    "retail-user": {
        "user_id": "synthetic-retail-user",
        "display_name": "Retail User",
        "role": "retail",
        "entitlement": "delayed market data",
    },
    "broker-user": {
        "user_id": "synthetic-broker-user",
        "display_name": "Broker User",
        "role": "broker",
        "entitlement": "delayed market data",
    },
}


def get_synthetic_user(user_id: str):
    return SYNTHETIC_USERS.get(user_id)
