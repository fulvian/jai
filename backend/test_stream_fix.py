import httpx
import json

def test_stream():
    print("Sending streaming query to Me4BrAIn...")
    with httpx.stream("POST", "http://localhost:8089/v1/engine/query", json={
        "query": "che tempo fa a Caltanissetta?",
        "stream": True,
        "session_id": "test-session-123"
    }, timeout=60.0) as r:
        if r.status_code != 200:
            print(f"Error: {r.status_code}")
            print(r.read())
            return
            
        for line in r.iter_lines():
            if line:
                print(line)

if __name__ == "__main__":
    test_stream()
