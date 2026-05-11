from pathlib import Path
from src.skills.manager import get_skill_manager
from datetime import datetime

mgr = get_skill_manager()
skill = mgr.get_skill('proposal-generator')
if not skill:
    print('Skill not found')
    raise SystemExit(1)
workspace_root = Path('rag_storage') / 'mcpp_drfp_t4'
if not workspace_root.exists():
    print('Workspace root not found:', workspace_root)
    raise SystemExit(1)
# create a fake run_dir
ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
run_dir = workspace_root / 'skill_runs' / skill.name / (ts + '_smoke')
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / 'artifacts').mkdir(exist_ok=True)
(run_dir / 'tool_outputs').mkdir(exist_ok=True)
# write response.md
resp = '# Smoke Run\n\nThis is a smoke test response to verify artifact emission.\n'
(run_dir / 'response.md').write_text(resp, encoding='utf-8')
# invoke emitter
try:
    mgr._auto_emit_artifacts(skill, run_dir)
    print('Emitter invoked; artifacts dir:', (run_dir / 'artifacts'))
    for p in (run_dir / 'artifacts').iterdir():
        print(' -', p.name)
    for p in (run_dir / 'tool_outputs').iterdir():
        print(' tool:', p.name)
except Exception as e:
    print('Emitter error:', e)
