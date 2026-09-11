"""Render inspectable Three.js scenes and fit the front projection to vector paths.

Use the existing project venv; pinned Three.js modules are reused from the jazz
study. No package installation or database access. Candidate output stays in scratch.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from fit_contours import fit_color_regions

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
parser = argparse.ArgumentParser()
parser.add_argument('--ids', nargs='*')
parser.add_argument('--render-only', action='store_true')
parser.add_argument('--fit-only', action='store_true')
parser.add_argument('--output', type=Path, default=ROOT / '.scratch/icon-corrections-20260909')
args = parser.parse_args()
out = args.output
out.mkdir(parents=True, exist_ok=True)
catalog = {i['id']: i for i in json.loads((ROOT / 'config/event-icons/catalog.json').read_text())['icons']}
host = 'http://icon-study.local/'
html = '''<!doctype html><script type="importmap">{"imports":{"three":"/three.module.js"}}</script>
<script type="module">
import * as THREE from 'three';
import {createModels} from '/scene.js';
const api=createModels(THREE);
for (const file of ['objects.js','people.js']) {
 try {const m=await import('/'+file);await m.extend(api);}catch(e){if(!String(e).includes('404'))throw e;}
}
const renderer=new THREE.WebGLRenderer({alpha:true,antialias:false,preserveDrawingBuffer:true});
renderer.setSize(1024,1024);renderer.setClearColor(0,0);
window.renderModel=(id,view='icon')=>{
 const root=api.models[id], scene=new THREE.Scene();scene.add(root);root.updateMatrixWorld(true);
 const bounds=new THREE.Box3().setFromObject(root), center=bounds.getCenter(new THREE.Vector3());
 const direction=view==='icon'?root.userData.camera:({front:[0,0,1],side:[1,.05,0],top:[0,1,.001],rear:[0,.12,-1]})[view];
 const camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,5000);
 camera.position.copy(center).add(new THREE.Vector3(...direction).normalize().multiplyScalar(500));camera.lookAt(center);camera.updateMatrixWorld(true);
 let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
 root.traverse(o=>{if(!o.isMesh)return;const attr=o.geometry.attributes.position,p=new THREE.Vector3();for(let i=0;i<attr.count;i++){p.fromBufferAttribute(attr,i).applyMatrix4(o.matrixWorld).applyMatrix4(camera.matrixWorldInverse);minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x);minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y);}});
 const extent=Math.max(maxX-minX,maxY-minY)*.55,mx=(maxX+minX)/2,my=(maxY+minY)/2;
 camera.left=mx-extent;camera.right=mx+extent;camera.top=my+extent;camera.bottom=my-extent;camera.updateProjectionMatrix();
 renderer.render(scene,camera);
 const eyes=[];root.traverse(o=>{if(o.userData.eye){const p=o.getWorldPosition(new THREE.Vector3()).project(camera);eyes.push([(p.x+1)*64,(1-p.y)*64]);}});
 const data=renderer.domElement.toDataURL('image/png');scene.remove(root);
 return {data,eyes,camera:{direction,extent,center:center.toArray()},bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()},geometry:root.toJSON(),checks:root.userData.checks||[]};
};
window.ids=Object.keys(api.models);window.ready=true;
</script>'''

if not args.fit_only:
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--enable-unsafe-swiftshader'])
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        def route(r):
            name=r.request.url.removeprefix(host)
            if not name:
                return r.fulfill(body=html,content_type='text/html')
            path=(ROOT / '.scratch/jazz-trio-3d' / name) if name.startswith('three.') else HERE / name
            if name.endswith(('GLTFLoader.js','BufferGeometryUtils.js')):
                path=ROOT/'.scratch/icon-corrections-20260909/assets/three'/Path(name).name
            if path.is_file():return r.fulfill(path=str(path),content_type='text/javascript')
            r.fulfill(status=404,body='404')
        page.route(host+'**',route)
        page.goto(host)
        try:page.wait_for_function('window.ready',timeout=20000)
        except Exception:raise RuntimeError(errors)
        ids=args.ids or page.evaluate('window.ids')
        for id in ids:
            folder=out/'models'/id;folder.mkdir(parents=True,exist_ok=True)
            for view in ['icon','front','side','top','rear']:
                data=page.evaluate('([id,view])=>window.renderModel(id,view)',[id,view])
                (folder/f'{view}.png').write_bytes(base64.b64decode(data.pop('data').split(',')[1]))
                if view=='icon':
                    (folder/'scene.json').write_text(json.dumps(data.pop('geometry')))
                    (folder/'projection.json').write_text(json.dumps(data,indent=2))
            print('Rendered',id,flush=True)
        browser.close()
else:
    ids=args.ids or [p.name for p in (out/'models').iterdir()]

if not args.render_only:
    for id in ids:
        folder=out/'models'/id
        projection=json.loads((folder/'projection.json').read_text())
        paths,regions=fit_color_regions(folder/'icon.png', tolerance=.28,min_area=.12,palette_distance=14,eye_centers=projection['eyes'])
        if id=='craft-pottery-wheel':
            pixels=np.array(Image.open(folder/'icon.png').convert('RGBA'))
            warm=(pixels[:,:,0].astype(float)>pixels[:,:,2]*1.25)&(pixels[:,:,3]>0)
            colors,counts=np.unique(pixels[:,:,:3][warm],axis=0,return_counts=True)
            base=np.zeros_like(pixels);base[warm,:3]=colors[counts.argmax()];base[warm,3]=255
            Image.fromarray(base).save(folder/'pot-underpaint.png')
            under,_=fit_color_regions(folder/'pot-underpaint.png',tolerance=.18,min_area=.12,palette_distance=14)
            paths=under+paths
        body=re.sub(r'fill="(#[0-9a-f]+)" stroke="\1"',r'color="\1"',''.join(paths))
        body=re.sub(r'l0(?: |(?=-))(-?\d+)',r'v\1',body)
        body=re.sub(r'l(-?\d+) 0(?=[A-Za-z])',r'h\1',body)
        stroke='2' if id=='craft-pottery-wheel' else '.20'
        title=catalog[id]['label'].replace('&','&amp;')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" fill="currentColor" stroke="currentColor" stroke-width="{stroke}" stroke-linejoin="round" fill-rule="evenodd"><title>{title}</title><g transform="scale(.25)">{body}</g></svg>\n'
        target=out/'candidates'/Path(catalog[id]['source']).name;target.parent.mkdir(exist_ok=True)
        target.write_text(svg)
        print(f'Fitted {id}: {len(svg.encode())} bytes, {regions} regions',flush=True)
