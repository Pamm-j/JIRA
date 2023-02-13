IS_PRODUCTION = True

def get_secret(secret_reference):
    secrets = {"MY_PASSWORD":"the_real_secret"}
    try:
        secrets[secret_reference]
    except Exception("no secret found"):
        return

def is_production():
    if IS_PRODUCTION:
        return True
    else:
        return False

