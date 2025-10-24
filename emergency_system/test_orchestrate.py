import requests

url = "https://dl.watson-orchestrate.ibm.com/build/agent/edit/89cdd69b-6578-46cb-a95c-3f2341a5381a"
api_key = "azE6dXNyX2U1NzUzNDU0LTVjZGUtM2UxMS04NTkyLWE1ZjA5ZDMwYmE3YzpaWmxTVHc4eGJJNGxLdjllMzd3MzNleHBCcjBLeEM5VWIwNktMRE8vZnR3PTpmUFc2"

headers = {
    "x-api-key": api_key
}


response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)

print("Status:", response.status_code)
print("Final URL:", response.url)
print("Redirects:", len(response.history))
print("Content-Type:", response.headers.get('Content-Type'))

# Try to decode JSON safely; fall back to raw text when not JSON
try:
    data = response.json()
    print("Connected successfully! JSON response:")
    print(data)
except Exception as exc:  # requests.JSONDecodeError or ValueError
    print("Connected successfully! But response body is not JSON (or empty).")
    # Print a short preview of the body to help debugging
    text = response.text or ''
    if not text.strip():
        print("<empty response body>")
    else:
        max_len = 2000
        print(text[:max_len])
        if len(text) > max_len:
            print("... (truncated)")

    # Also print headers for debugging reasons
    print('\nResponse headers:')
    for k, v in response.headers.items():
        print(f"{k}: {v}")