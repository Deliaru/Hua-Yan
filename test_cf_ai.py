import requests

WORKER_URL = "https://jev-proxy.xi1092183542.workers.dev"

payload = {
    "state": "纯锦纶在 75℃ 下使用溢流染色机，色花问题得到明显改善，升温时间节省 79min。",
    "question": "抽取结论：'升温时间节省 79min' 是否有原文明确证据支持？"
}

print("📡 正在调用 Cloudflare Workers AI 进行事实判定...")
response = requests.post(WORKER_URL, json=payload, timeout=20)

if response.status_code == 200:
    print("✅ 判定返回成功:")
    print(response.json())
else:
    print("❌ 请求失败:", response.status_code, response.text)