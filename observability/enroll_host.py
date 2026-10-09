"""One-time local enrollment through the already configured authenticated gateway.

This is TOFU, not independent host verification. Subsequent collectors reject drift.
"""
from pathlib import Path
from mcp_servers.srv_api_gateway_mcp import _get_ssh_client, HOST, PORT

root=Path(__file__).resolve().parents[1]
pin=root/'.runtime'/'known_hosts'
pin.parent.mkdir(parents=True,exist_ok=True)
if pin.exists():
    raise SystemExit('Host already pinned. Refusing automatic replacement.')
client=_get_ssh_client()
try:
    key=client.get_transport().get_remote_server_key()
    name=HOST if PORT==22 else f'[{HOST}]:{PORT}'
    pin.write_text(f'{name} {key.get_name()} {key.get_base64()}\n',encoding='ascii')
    print('Public host identity enrolled locally. Future drift fails closed.')
finally:
    client.close()
