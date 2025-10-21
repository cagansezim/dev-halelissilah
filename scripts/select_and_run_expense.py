#!/usr/bin/env python3
import os, sys, json, time, argparse, requests
from typing import Any, Dict, List, Optional
from packages.clients.internal_api.client import InternalAPIClient  # type: ignore

def ask(msg, default=None):
    s = input(f"{msg}{' ['+default+']' if default else ''}: ").strip()
    return s or (default or "")

def list_expenses(api: InternalAPIClient, start:str, end:str) -> List[Dict[str,Any]]:
    res = api.list_expenses(start_date=start or "", end_date=end or "")
    data = res
    if isinstance(res, dict) and "data" in res:
        data = res["data"]
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected list_expenses shape: {res}")
    return data

def extract_files(expense: Dict[str,Any]) -> List[Dict[str,Any]]:
    out=[]
    kod = expense.get("Kod") or expense.get("kod") or expense.get("Masraf",{}).get("Kod")
    files = expense.get("files") or expense.get("Dosyalar")
    if not files and "MasrafAlt" in expense:
        for _, line in (expense["MasrafAlt"] or {}).items():
            dmap = (line or {}).get("Dosya") or {}
            for _, f in dmap.items():
                out.append({
                    "kod": kod,
                    "fileId": f.get("Kod"),
                    "fileHash": f.get("Hash"),
                    "filename": f.get("OrjinalAdi") or f.get("Adi"),
                    "mime": f.get("MimeType") or "application/octet-stream",
                    "size": f.get("Size") or 0
                })
        return out
    for f in (files or []):
        out.append({
            "kod": kod,
            "fileId": f.get("Kod") or f.get("fileId"),
            "fileHash": f.get("Hash") or f.get("fileHash"),
            "filename": f.get("OrjinalAdi") or f.get("name") or "file",
            "mime": f.get("MimeType") or f.get("mime") or "application/octet-stream",
            "size": f.get("Size") or f.get("size") or 0
        })
    return out

def pick_one(items: List[Dict[str,Any]], label: str) -> Dict[str,Any]:
    for i,it in enumerate(items,1):
        desc = it.get("Aciklama") or it.get("description") or ""
        kod  = it.get("Kod") or it.get("kod") or it.get("Masraf",{}).get("Kod")
        print(f"[{i}] Kod={kod}  {desc}")
    idx = int(ask(f"Pick {label} #", "1"))
    return items[idx-1]

def pick_files(files: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    for i,f in enumerate(files,1):
        print(f"[{i}] kod={f['kod']} fileId={f['fileId']} hash={f['fileHash']} mime={f['mime']}")
    raw = ask("Choose file numbers (comma or 'all')", "1")
    if raw.lower()=="all":
        return files
    idxs = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
    return [files[i-1] for i in idxs]

def submit_refs(extractor_base:str, description:str, refs: List[Dict[str,Any]]) -> str:
    files=[]
    for r in refs:
        files.append({
            "filename": r["filename"] or f"{r['fileId']}.bin",
            "mime": r["mime"],
            "size": int(r["size"] or 0),
            "ref": {"kod": r["kod"], "fileId": r["fileId"], "fileHash": r["fileHash"]}
        })
    body={"description":description,"files":files}
    r = requests.post(f"{extractor_base}/extractor/requests", json=body, timeout=60)
    r.raise_for_status()
    return r.json()["request_id"]

def watch(extractor_base:str, rid:str):
    while True:
        s = requests.get(f"{extractor_base}/extractor/requests/{rid}", timeout=30).json()
        print(s)
        if s.get("state") in ("done","failed","needs_review"):
            break
        time.sleep(1)
    return s.get("state")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal", default=os.getenv("INTERNAL_API_BASE","http://localhost:8080/api"))
    ap.add_argument("--email", default=os.getenv("INTERNAL_API_EMAIL","admin@example.com"))
    ap.add_argument("--password", default=os.getenv("INTERNAL_API_PASSWORD","secret"))
    ap.add_argument("--extractor", default=os.getenv("EXTRACTOR_BASE","http://localhost:8081"))
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--q", default="")
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--kod", type=int)
    ap.add_argument("--file-id", type=int)
    ap.add_argument("--file-hash", type=str)
    ap.add_argument("--description", default="")
    args = ap.parse_args()

    if args.submit-only:
        if not (args.kod and args.file_id and args.file_hash):
            print("--submit-only requires --kod --file-id --file-hash"); sys.exit(2)
        ref = [{
            "kod": args.kod, "fileId": args.file_id, "fileHash": args.file_hash,
            "filename": f"{args.file_id}.bin", "mime": "application/octet-stream", "size": 0
        }]
        rid = submit_refs(args.extractor, args.description, ref)
        print("RID:", rid)
        print("Status:", watch(args.extractor, rid))
        print("Review:", f"{args.extractor}/extractor/review/{rid}")
        return

    api = InternalAPIClient(
        base_url=args.internal,
        auth_url=os.getenv("INTERNAL_API_AUTH_URL","/auth/login"),
        list_url=os.getenv("INTERNAL_API_LIST_URL","/expenses/list"),
        json_url=os.getenv("INTERNAL_API_JSON_URL","/expenses/json"),
        file_url=os.getenv("INTERNAL_API_FILE_URL","/expenses/file"),
        email=args.email,
        password=args.password,
        timeout=int(os.getenv("INTERNAL_API_TIMEOUT_SEC","30")),
    )

    print("Fetching expenses ...")
    exps = list_expenses(api, args.start, args.end)
    if not exps:
        print("No expenses found."); return
    exp = pick_one(exps, "expense")
    files = extract_files(exp)
    if not files:
        print("No files on this expense."); return
    chosen = pick_files(files)
    desc = ask("Description to send", (exp.get("Aciklama") or ""))

    rid = submit_refs(args.extractor, desc, chosen)
    print("RID:", rid)
    print("Watching job ...")
    state = watch(args.extractor, rid)
    print("Final state:", state)
    print("Review URL:", f"{args.extractor}/extractor/review/{rid}")
    print(f"Artifacts: MinIO → pruva-files/expenses/{rid}/")
if __name__ == "__main__":
    main()
