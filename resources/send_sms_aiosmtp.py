import requests

baseParams = {
    'username': 'testuser',
    'password': 'testpass',
    'to': '447428555555',
    'from': '447000111222',
    'content': 'Hello',
    'dlr': 'yes',
    'dlr-method': 'POST',
    'dlr-url': 'http://172.17.0.1:8080/dlr',
    'dlr-level': 3
}

try:
    resp = requests.get("http://0.0.0.0:8080/send", params=baseParams)
    print(resp.text)
except Exception as err:
    print(err)
