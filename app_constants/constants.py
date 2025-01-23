class CommonConstants:
    status = "status"
    message = "message"
    failed = "failed"
    data = "data"
    success = "success"
    login_token = 'login-token'
    auth_token = "auth-token"
    role = "role"
    content_disposition = "Content-Disposition"
    id = "id"
    captcha_value = "captcha_value"
    captcha_key = "captcha_key"
    sent_list = "sent_list"
    body = "body"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    options = "options"
    status_code = "status_code"
    none = None


class Secrets:
    permanent_token = "9c68f7ab-4fee-4e3e-94a8-849d525861c7"
    cookie_encryption_private_key = "#ilenskey@rock1#"
    issuer = "ilens"
    alg = "RS256"
    leeway_in_mins = 10
    decrypt_encrypt_secret_key = "kliLensKLiLensKL"



class RESTAPIMethods:
    get: str = "GET"
    post: str = "POST"
    put: str = "PUT"
    get_raw_response: str = "GET_RAW"
