"""Observação pós-deploy pelo gateway MCP existente; nenhuma ação corretiva."""
import argparse, asyncio, json, re, shlex, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastmcp import Client
from mcp_servers.srv_api_gateway_mcp import mcp
async def main(args):
    directory = "/home/ti-kiosk/hub-homolog" if args.environment == "hml" else "/home/ti-kiosk/hub"
    command = "cd " + shlex.quote(directory) + " && node scripts/post-deploy-check.js --environment " + shlex.quote(args.environment) + " --expected-sha " + shlex.quote(args.sha) + " --samples 3 --interval-ms 1000"
    if args.since:
        command += " --since " + shlex.quote(args.since)
    async with Client(mcp) as client:
        result = await client.call_tool("srv_api_run_safe_command", {"command": command})
        payload = result.data
        if not isinstance(payload, dict):
            payload = json.loads(next(item.text for item in result.content if getattr(item,"text",None)))
        if not payload.get("success") and not payload.get("stdout", "").lstrip().startswith("{"):
            print(json.dumps({"ok":False,"environment":args.environment,"error":payload.get("stderr") or payload.get("stdout")},ensure_ascii=False))
            return 1
        report = json.loads(payload["stdout"])
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report.get("ok") else 1
if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--environment",choices=["hml","production"],default="hml")
    parser.add_argument("--sha",required=True)
    parser.add_argument("--since")
    args=parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}",args.sha): parser.error("SHA completo obrigatório")
    raise SystemExit(asyncio.run(main(args)))
