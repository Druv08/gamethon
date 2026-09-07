"""Extract the supplied four-enemy roster; original art is strictly read-only.

Uses the existing PNG, sheet resampler and border-connected background removal.
Mappings below were inspected against the actual silhouettes and attack effects.
No generated art, mirroring, frame interpolation or dropped animation frames.
Run with the engine's bundled Python, then PTK_GenerateEnemyRoster.py in Unreal.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import median
from collections import deque

import ptk_png
import ptk_sheet
from ExtractGuardIdle import remove_background

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\druvk\Downloads\gamethon pics\design 2d pics')
DIRECTIONS = ['Down', 'Up', 'Left', 'Right']
# Walk DU, Walk LR, Attack DU, Attack LR, Death (columns, rows).
SOURCES = {
    'Infiltrator': ['b75f3e47-5090-445a-90df-0a5186c2f275', 'fdf25c08-0f75-4037-a3ce-18afcbe4bb91', '0189ac42-1e63-42b7-8715-d649578feaf9', '1366cd2b-0b7d-4edd-9122-6d29aa58c6da', '7c381f7b-11d2-4d88-a5c9-ef346a0b280d', (4, 2)],
    'Hijacker': ['25c4319b-375a-4588-874e-01976c4f39b3', '6ba694d9-388d-458e-b03a-92b62e2fde87', '4dd1d538-5341-48a0-9987-c7a77bf4d99f', '09a681f6-b7e0-4e4f-a035-2ae6657f7704', '7a7344d5-4283-403b-a719-e9a91fa6d4ab', (4, 2)],
    'Encrypter': ['2b7f20cd-808b-4bc5-be47-9535f240e906', '48b2d659-4a74-487d-95a8-6c5816cc8050', 'f9ff1f56-b047-42f2-a375-58ca73186ee0', 'b11b8f16-fabe-4de0-a402-be919e8256e1', 'e611f28b-38e0-4dd2-8310-cfaefa82ecbd', (8, 1)],
    'Exfiltrator': ['63a7191b-1dae-402e-897e-0c9f2d95887f', '26f6811b-eb0b-405a-a21d-445b6b7083ff', '48df17b1-8f23-49e6-b639-ab0198dd7a94', 'e7f2df86-4fa2-46a6-95a7-f68e151f4c78', 'eb4ab856-6376-4cc6-8ecc-0f6578ad1889', (8, 1)],
}


def effect(r, g, b):
    # Bright energy only; dark armour and cloth remain geometry references.
    return max(r, g, b) > 175 and max(r, g, b) - min(r, g, b) > 70


def metrics(cell):
    body, full, w, h = ptk_sheet.build_masks(cell, 128, effect)
    result = ptk_sheet.ground_anchor(body, w, h)
    assert result, 'empty body'
    # Hip centroid is more stable than cloak/weapon silhouette centre.
    y0 = int(result['bottom'] - result['height'] * .55)
    y1 = int(result['bottom'] - result['height'] * .35)
    xs = [x for y in range(max(0, y0), y1 + 1) for x in range(w) if body[y*w+x]]
    if xs:
        result['centre'] = sum(xs) / len(xs)
    return result


def split_row(sheet, y0, y1, columns, rows=1, separate_effect=False):
    """Separate connected silhouettes even where their horizontal bounds overlap.

    Eight largest islands are the bodies; detached pixels/effects belong to the
    nearest body bounds. Every opaque source pixel is retained exactly once.
    Uniform local origins preserve the source lunge rather than recentering it.
    """
    width, height = sheet.width, y1-y0
    mask=bytearray(width*height)
    for y in range(height):
        for x in range(width):
            r,g,b,a=sheet.get(x,y+y0)
            mask[y*width+x]=a>=128 and (not separate_effect or not effect(r,g,b))
    parts=[]
    for start in range(len(mask)):
        if not mask[start]: continue
        mask[start]=0;queue=deque([start]);points=[]
        while queue:
            k=queue.popleft();points.append(k);y,x=divmod(k,width)
            for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0<=xx<width and 0<=yy<height:
                    nk=yy*width+xx
                    if mask[nk]: mask[nk]=0;queue.append(nk)
        xs=[k%width for k in points];ys=[k//width for k in points]
        parts.append((points,(min(xs),min(ys),max(xs),max(ys))))
    parts.sort(key=lambda p:len(p[0]),reverse=True)
    ranked=sorted(parts[:columns*rows],key=lambda p:(p[1][1]+p[1][3])/2)
    bodies=[]
    for r in range(rows):
        bodies.extend(sorted(ranked[r*columns:(r+1)*columns],key=lambda p:(p[1][0]+p[1][2])/2))
    assert len(bodies)==columns*rows
    pitch=width/columns
    for col,(_,box) in enumerate(bodies):
        assert abs((box[0]+box[2])/2-(col%columns+.5)*pitch)<pitch*.65, ('Merged source bodies',col,box)
    cells=[ptk_png.Image(math.ceil(pitch*3),height) for _ in bodies]
    assigned=bytearray(width*height)
    def distance(box, other):
        dx=max(box[0]-other[2],other[0]-box[2],0)
        dy=max(box[1]-other[3],other[1]-box[3],0)
        return dx*dx+dy*dy
    for points,box in parts:
        own=next((c for c,b in enumerate(bodies) if points is b[0]),None)
        col=own if own is not None else min(range(len(bodies)),key=lambda c:(distance(box,bodies[c][1]),abs((box[0]+box[2])-(bodies[c][1][0]+bodies[c][1][2]))))
        origin=int(round((col%columns-1)*pitch))
        for k in points:
            y,x=divmod(k,width);xx=x-origin
            assert 0<=xx<cells[col].width, (col,box,bodies[col][1],len(points),xx)
            cells[col].set(xx,y,sheet.get(x,y+y0))
            assigned[k]=1
    # Coloured effects can bridge two source poses. Assign those pixels after
    # separating the dark bodies, so a beam cannot merge two whole characters.
    for y in range(height):
        for x in range(width):
            if assigned[y*width+x] or sheet.get(x,y+y0)[3]<128:continue
            box=(x,y,x,y)
            col=min(range(len(bodies)),key=lambda c:(distance(box,bodies[c][1]),abs(2*x-(bodies[c][1][0]+bodies[c][1][2]))))
            xx=x-int(round((col%columns-1)*pitch))
            assert 0<=xx<cells[col].width
            cells[col].set(xx,y,sheet.get(x,y+y0))
    return cells


def main():
    for name, files in SOURCES.items():
        if len(sys.argv)>1 and name not in sys.argv[1:]:continue
        print('Measuring', name, flush=True)
        source = SOURCE / (name.lower() + ' pics')
        dest = ROOT / 'ArtSource/Characters/Enemies' / name
        frames = dest / 'Frames'
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.png')}
        plans = []
        target_height = 124.0 if name == 'Encrypter' else 116.0
        for index, filename in enumerate(files[:5]):
            print('  sheet',filename,flush=True)
            anim = 'Walk' if index < 2 else 'Attack' if index < 4 else 'Death'
            cols, rows = files[5] if anim == 'Death' else (8, 2)
            directions = None if anim == 'Death' else DIRECTIONS[:2] if index % 2 == 0 else DIRECTIONS[2:]
            sheet = ptk_png.read_png(str(source / (filename + '.png')))
            bands = ptk_sheet.find_row_bands(sheet, rows)
            if bands and len(bands)==rows:
                cells = [split_row(sheet,y0,y1+1,cols,separate_effect=name=='Exfiltrator') for y0,y1 in bands]
            else:
                flat=split_row(sheet,0,sheet.height,cols,rows,separate_effect=name=='Exfiltrator')
                cells=[flat[r*cols:(r+1)*cols] for r in range(rows)]
            measured = [[metrics(cell) for cell in row] for row in cells]
            # Rest poses define body scale, so crouches and death collapse are preserved.
            reference = (measured[0][0]['height'] if anim == 'Death' else
                         median(m['height'] for row in measured for m in (row if anim == 'Walk' else [row[0], row[-1]])))
            scale = target_height / reference
            for r in range(rows):
                anchors = ptk_sheet.anchors_for_row(measured[r], anim == 'Walk')
                for c in range(cols):
                    direction = directions[r] if directions else None
                    stem = (f'{anim}_{direction}_{c+1:02}' if direction else f'Death_{r*cols+c+1:02}')
                    plans.append(dict(stem=stem, folder=f'{anim}/{direction}' if direction else anim,
                                      cell=cells[r][c], anchor=anchors[c], scale=scale, source=filename,
                                      row=r, column=c))

        # Real standing poses from the supplied presentation cards, excluding labels.
        card = ptk_png.read_png(str(source / (name.lower() + '.png')))
        boxes=([(90,345,500,740),(620,345,1020,730),(105,830,505,1180),(615,830,1020,1180)] if name=='Exfiltrator' else
               [(80,335,545,710),(575,335,1040,710),(80,790,545,1170),(575,790,1040,1170)])
        for direction, box in zip(DIRECTIONS, boxes):
            cell = card.crop(*box)
            remove_background(cell, 14)
            # Remove disconnected presentation remnants; keep the supplied body.
            ptk_sheet.clean_islands(cell, (cell.width//2, cell.height//2), effect, max_gap=8)
            m = metrics(cell)
            plans.append(dict(stem='Idle_'+direction, folder='Idle', cell=cell,
                              anchor=(m['centre'], m['bottom']), scale=target_height/m['height'],
                              source=name.lower()+'.png', crop=box))

        # Measure every opaque extent BEFORE choosing canvas, including death/effects.
        need = [0.,0.,0.,0.]
        for p in plans:
            x0,y0,x1,y1 = p['cell'].opaque_bounds(127)
            ax,ay = p['anchor'];s=p['scale']
            need = [max(a,b) for a,b in zip(need,[(ax-x0)*s,(x1-ax)*s,(ay-y0)*s,(y1-ay)*s])]
        px = max(112, math.ceil(max(need[:2])+20))
        py = max(200, math.ceil(need[2]+20))
        canvas = (math.ceil((2*px+1)/16)*16, math.ceil((py+need[3]+21)/16)*16)
        pivot = (px,py)
        manifest = dict(name=name, canvas=canvas, pivot=pivot, body_height=target_height,
                        measured_extent=need, source_sha256=hashes, frames=[])
        if name=='Exfiltrator':
            # Measured source rectangles, read from the original effects, before
            # any character segmentation. Their own background alpha is retained.
            effect_boxes={'Down':(1165,230,1270,364),'Up':(1170,367,1275,465),
                          'Left':(1005,168,1145,272),'Right':(1300,493,1425,594),
                          'Impact':(1395,238,1600,373)}
            for direction,box in effect_boxes.items():
                facing='Down' if direction=='Impact' else direction
                p=next(p for p in plans if p['stem']=='Attack_'+facing+'_05')
                original=ptk_png.read_png(str(source/(p['source']+'.png')))
                cell=original.crop(*box)
                for k in range(cell.width*cell.height):
                    r,g,b,a=cell.px[k*4:k*4+4]
                    if not (g>120 and g-r>45 and g-b>25):cell.px[k*4+3]=0
                bounds=cell.opaque_bounds(127)
                assert bounds
                anchor=((bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2)
                stem='Impact_01' if direction=='Impact' else 'Flight_'+direction+'_01'
                plans.append(dict(stem=stem,folder='Projectile',cell=cell,anchor=anchor,
                                  scale=p['scale'],source=p['source'],crop=box,canvas=(129,129),pivot=(64,64)))
            for p in plans:
                if not p['stem'].startswith('Attack_'):continue
                cell=p['cell']
                body,_,w,h=ptk_sheet.build_masks(cell,128,lambda r,g,b:g>40 and g>r*1.6 and g>b*1.3)
                largest=[]
                for k in range(w*h):
                    if not body[k]:continue
                    body[k]=0;q=deque([k]);part=[]
                    while q:
                        v=q.popleft();part.append(v);yy,xx=divmod(v,w)
                        for nx,ny in ((xx-1,yy),(xx+1,yy),(xx,yy-1),(xx,yy+1)):
                            if 0<=nx<w and 0<=ny<h and body[ny*w+nx]:
                                body[ny*w+nx]=0;q.append(ny*w+nx)
                    if len(part)>len(largest):largest=part
                x0=min(v%w for v in largest)-2;x1=max(v%w for v in largest)+2
                y0=min(v//w for v in largest)-2;y1=max(v//w for v in largest)+2
                for y in range(h):
                    for x in range(w):
                        if x<x0 or x>x1 or y<y0 or y>y1:
                            cell.px[(y*w+x)*4+3]=0
        overview = ptk_png.Image(canvas[0]*8, canvas[1]*math.ceil(len(plans)/8))
        for i,p in enumerate(plans):
            cell=p['cell'];ax,ay=p['anchor']
            frame=ptk_sheet.render_frame(cell,0,0,cell.width,cell.height,ax,ay,p['scale'],p.get('canvas',canvas),p.get('pivot',pivot),fence_fraction=2)
            ptk_sheet.harden_alpha(frame)
            assert not ptk_sheet.border_contact(frame), p['stem']+' clipped'
            out=frames/p['folder']/(p['stem']+'.png');out.parent.mkdir(parents=True,exist_ok=True)
            ptk_png.write_png(str(out),frame)
            overview.paste(frame,(i%8)*canvas[0],(i//8)*canvas[1])
            manifest['frames'].append({k:v for k,v in p.items() if k!='cell'} | {'bounds':frame.opaque_bounds(127)})
        ptk_png.write_png(str(dest/'Overview.png'),overview)
        (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
        assert hashes == {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.png')}
        print(name, len(plans), 'frames; canvas',canvas,'pivot',pivot,'no border contact',flush=True)


if __name__ == '__main__':
    main()
