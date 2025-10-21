from typing import Dict, Any, List, Tuple
from ..core.models import ExpenseJSON

def _f(x): 
    try: return float(x)
    except: return 0.0

def merge_and_validate(dv: Dict[str,Any]|None, dt: Dict[str,Any]|None) -> Tuple[ExpenseJSON, List[Dict[str,Any]], float]:
    v = dv or {}; t = dt or {}
    flags: List[Dict[str,Any]] = []

    m = {}
    m["Kod"] = t.get("Masraf",{}).get("Kod") or v.get("Masraf",{}).get("Kod")
    for key in ["BaslangicTarihi","BitisTarihi"]:
        m[key] = v.get("Masraf",{}).get(key) or t.get("Masraf",{}).get(key)
    m["Aciklama"] = t.get("Masraf",{}).get("Aciklama") or v.get("Masraf",{}).get("Aciklama")
    m["Bolum"] = t.get("Masraf",{}).get("Bolum") or v.get("Masraf",{}).get("Bolum")
    m["Hash"]  = t.get("Masraf",{}).get("Hash")  or v.get("Masraf",{}).get("Hash")

    lines_v = v.get("MasrafAlt", []) or []
    lines_t = t.get("MasrafAlt", []) or []
    lines = lines_t if len(lines_t)>=len(lines_v) else lines_v

    # math check
    calc = sum([_f(li.get("BirimMasrafTutari",0))*_f(li.get("Miktar",1)) for li in lines])
    total = next((_f(li.get("ToplamMasrafTutari")) for li in lines if li.get("ToplamMasrafTutari")), None)
    if total is not None and abs(calc-total)>0.01:
        flags.append({"path":"MasrafAlt[0].ToplamMasrafTutari","issue":"sum_mismatch","detail":f"{calc} vs {total}"})

    dosya = t.get("Dosya") or v.get("Dosya") or []
    merged = ExpenseJSON(Masraf=m, MasrafAlt=lines, Dosya=dosya)
    conf = 0.95 if not flags else 0.6
    return merged, flags, conf
