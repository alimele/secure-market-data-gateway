import jwt, datetime, json

SECRET = "demo-secret-key-not-for-production"

tokens = {
  "broker_realtime": jwt.encode({"sub":"manual-broker","role":"BROKER","entitlements":["MARKET_DATA_REALTIME"],"aud":"adx-demo-gateway","iss":"adx-demo-idp","exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)}, SECRET, algorithm="HS256"),
  "retail":          jwt.encode({"sub":"manual-retail","role":"RETAIL","entitlements":[],"aud":"adx-demo-gateway","iss":"adx-demo-idp","exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)}, SECRET, algorithm="HS256"),
  "broker_no_ent":   jwt.encode({"sub":"manual-noent","role":"BROKER","entitlements":[],"aud":"adx-demo-gateway","iss":"adx-demo-idp","exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)}, SECRET, algorithm="HS256"),
}

for name, tok in tokens.items():
    print(f"{name}: {tok}")
    