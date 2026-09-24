from __future__ import annotations
import json
from pathlib import Path
from core import atomic_json, sha256_file, utc_now


def visual_compare_command(args)->int:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("visual-compare requires Pillow: python -m pip install pillow") from exc
    baseline=Path(args.baseline).resolve(); candidate=Path(args.candidate).resolve(); out=Path(args.out_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    a=Image.open(baseline).convert("RGBA"); b=Image.open(candidate).convert("RGBA")
    if a.size!=b.size:
        result={"schema":"BASARA_FOUNDRY_VISUAL_EVIDENCE_V1","created_utc":utc_now(),"pass":False,"reason":"dimension_mismatch","baseline_size":a.size,"candidate_size":b.size}
        atomic_json(out/"visual_evidence.json",result); print(json.dumps(result,indent=2)); return 5
    mask=None; mask_hash=None
    if args.mask:
        mp=Path(args.mask).resolve(); mask=Image.open(mp).convert("L")
        if mask.size!=a.size:
            raise SystemExit(f"Mask dimensions {mask.size} do not match screenshot {a.size}")
        mask_hash=sha256_file(mp)
    pa=a.load(); pb=b.load(); pm=mask.load() if mask else None
    diff=Image.new("RGBA",a.size,(0,0,0,0)); pd=diff.load()
    changed=0; considered=0; max_delta=0
    for y in range(a.height):
        for x in range(a.width):
            if pm is not None and pm[x,y] != 0:
                continue
            considered+=1
            delta=max(abs(pa[x,y][i]-pb[x,y][i]) for i in range(4))
            max_delta=max(max_delta,delta)
            if delta>args.pixel_threshold:
                changed+=1
                pd[x,y]=(255,0,0,255)
    ratio=(changed/considered) if considered else 0.0
    passed=ratio<=args.max_changed_ratio
    diff_path=out/"visual_diff.png"; diff.save(diff_path)
    result={"schema":"BASARA_FOUNDRY_VISUAL_EVIDENCE_V1","created_utc":utc_now(),"snapshot_id":args.snapshot_id,
            "baseline":{"path":str(baseline),"sha256":sha256_file(baseline)},"candidate":{"path":str(candidate),"sha256":sha256_file(candidate)},
            "mask":{"path":str(Path(args.mask).resolve()),"sha256":mask_hash} if args.mask else None,
            "width":a.width,"height":a.height,"pixel_threshold":args.pixel_threshold,"max_changed_ratio":args.max_changed_ratio,
            "considered_pixels":considered,"changed_pixels":changed,"changed_ratio":ratio,"max_channel_delta":max_delta,
            "diff":{"path":str(diff_path),"sha256":sha256_file(diff_path)},"pass":passed}
    atomic_json(out/"visual_evidence.json",result); print(json.dumps(result,indent=2)); return 0 if passed else 5
