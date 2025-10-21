import time, json, itertools
from typing import Dict, Any, List, Tuple
from ..config import settings
from .path_text import run_text
from .path_vision import run_vision
from .merge_validate import merge_and_validate

def _csv(lst: str) -> List[str]:
    return [x.strip() for x in lst.split(",") if x.strip()]

async def run_all_strategies(png_pages: List[bytes], page_texts: List[str], description: str|None, email: str|None):
    text_models  = _csv(settings.TEXT_MODELS)
    vision_models= _csv(settings.VISION_MODELS)
    ocrs         = _csv(settings.OCR_ENGINES)   # for logging only; OCR already ran upstream
    combos = []
    # Evaluate: text-only, vision-only, both (for each pair)
    for tm in text_models:
        t0=time.time(); dt = await run_text(tm, description, page_texts, None, email); t1=time.time()
        combos.append(("text-only", tm, None, t1-t0, dt, None))
    for vm in vision_models:
        t0=time.time(); dv = await run_vision(vm, png_pages, description); t1=time.time()
        combos.append(("vision-only", None, vm, t1-t0, None, dv))
    for tm, vm in itertools.product(text_models, vision_models):
        t0=time.time()
        dt = await run_text(tm, description, page_texts, None, email)
        dv = await run_vision(vm, png_pages, description)
        merged, flags, conf = merge_and_validate(dv, dt)
        t1=time.time()
        combos.append(("both-merge", tm, vm, t1-t0, dt, dv))

    # Now produce merged winner per simple rule (fewest flags, highest conf after merge)
    best = None
    best_score = -1.0
    results = []
    for mode, tm, vm, secs, dt, dv in combos:
        merged, flags, conf = merge_and_validate(dv, dt)
        score = conf - 0.05*len(flags)
        results.append({
            "mode": mode, "text_model": tm, "vision_model": vm,
            "seconds": secs, "flags": flags, "confidence": conf,
            "merged": merged.dict()
        })
        if score>best_score:
            best, best_score = results[-1], score

    # Persist a full evaluation report
    report = {
        "ocr_engines": ocrs,
        "text_models": text_models,
        "vision_models": vision_models,
        "comparisons": results,
        "chosen": best
    }
    return report
