import requests
import time

baseParams = {
    'username': 'testuser',
    'password': 'testpass',
    'to': '447428555555',
    'from': '447000111222',
    'content': 'Hello',
    'dlr': 'yes',
    'dlr-method': 'POST',
    'dlr-url': 'http://127.0.0.1:8082/dlr',
    'dlr-level': 3
}

try:
    start = time.perf_counter()
    resp = requests.get("http://0.0.0.0:8080/send", params=baseParams)
    end = time.perf_counter()
    print(resp.text)
    print('Time taken {0}'.format(end-start))
except Exception as err:
    print(err)
