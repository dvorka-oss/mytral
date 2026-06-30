import re, json

MAP = {
 'chest':'pecs','deltoids':'shoulders','biceps':'biceps','triceps':'triceps',
 'forearm':'forearms','abs':'abs','obliques':'obliques','trapezius':'traps',
 'upper-back':'lats','lower-back':'lower_back','gluteal':'glutes',
 'quadriceps':'quads','hamstring':'hamstrings','calves':'calves','tibialis':'calves',
 'neck':'neck','adductors':'hip_flexors',
}
SILH = {'head','hair','hands','feet'}
JOINTS = {'knees':'knee','ankles':'ankle'}
NAME = {'pecs':'Pectorals','shoulders':'Deltoid','biceps':'Biceps','triceps':'Triceps',
 'forearms':'Forearm','abs':'Abs','obliques':'Obliques','traps':'Trapezius','lats':'Lats/Upper back',
 'lower_back':'Lower back','glutes':'Glutes','quads':'Quadriceps','hamstrings':'Hamstrings',
 'calves':'Calves','neck':'Neck','hip_flexors':'Adductors'}

def parse(fn):
    t = open(fn).read()
    # split into slug blocks
    parts = re.split(r'slug:\s*"([^"]+)"', t)
    out=[]  # (slug, [paths])
    # parts: [pre, slug1, body1, slug2, body2, ...]
    for i in range(1,len(parts),2):
        slug=parts[i]; body=parts[i+1]
        paths=re.findall(r'"(M[^"]*)"', body)
        out.append((slug,paths))
    return out

def emit(fn, side):
    rows=parse(fn)
    frags=[]
    for slug,paths in rows:
        if not paths: continue
        if slug in SILH:
            cls='silh'; attr=''
        elif slug in JOINTS:
            cls='joint'; attr=f' data-part-id="{side}-{JOINTS[slug]}"'
        elif slug in MAP:
            key=MAP[slug]; cls='m'; attr=f' data-muscle-key="{key}" data-name="{NAME[key]}"'
        else:
            cls='silh'; attr=''  # fallback
        for p in paths:
            frags.append(f'<path class="{cls}"{attr} d="{p}"/>')
    return "\n".join(frags)

# outline from wrapper
w=open('wrapper.tsx').read()
ds=re.findall(r'd="(M[^"]+)"', w)
# first long one is front, second back
outline_front = max([d for d in ds if d.count(' ')>200 and float(d.split()[1])<724], key=len, default='')
outline_back  = max([d for d in ds if d.count(' ')>200 and float(d.split()[1])>=724], key=len, default='')

open('front.frag','w').write(emit('bodyFront.ts','front'))
open('back.frag','w').write(emit('bodyBack.ts','back'))
open('outline.json','w').write(json.dumps({'front':outline_front,'back':outline_back}))
print("front frags:", emit('bodyFront.ts','front').count('<path'))
print("back frags:", emit('bodyBack.ts','back').count('<path'))
print("outline front len:", len(outline_front), "back len:", len(outline_back))
