"""Explore EBA open data API to find Pillar 3 datasets."""
import requests

BASE = "https://data.eba.europa.eu/api/explore/v2.1"

# List datasets
print("=== EBA Open Data API — datasets ===")
r = requests.get(f"{BASE}/catalog/datasets")
if r.status_code == 200:
    data = r.json()
    print(f"Total datasets: {data.get('total_count', '?')}")
    for d in data.get('results', []):
        ds_id = d['dataset_id']
        title = d.get('title', '?')
        print(f"  {ds_id}: {title[:100]}")
else:
    print(f"Error: {r.status_code}")
    print(r.text[:500])

# Try to find Pillar 3
print("\n=== Searching for 'pillar' ===")
r2 = requests.get(f"{BASE}/catalog/datasets", params={"where": 'title like "%pillar%"', "limit": 10})
if r2.status_code == 200:
    d2 = r2.json()
    for d in d2.get('results', []):
        print(f"  {d['dataset_id']}: {d.get('title', '?')[:100]}")
else:
    print(f"Error: {r2.status_code}")