import requests
r = requests.get('http://192.168.0.9:11434/api/ps', timeout=5)
print(f'Status: {r.status_code}')
data = r.json()
models = data.get('models', [])
print(f'Models loaded: {len(models)}')
for m in models:
    vram = m.get('size_vram')
    if vram:
        print(f"  {m['name']}: {vram/(1024**3):.1f}GB")
