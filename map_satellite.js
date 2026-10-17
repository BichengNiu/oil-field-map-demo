// Sentinel-2 L2A via the public Microsoft Planetary Computer STAC/Data APIs.
// Queries run only after an explicit imagery action. No keys, polling or DB writes.
const sentinelEndpoint = 'https://planetarycomputer.microsoft.com/api/stac/v1';
const sentinelDataEndpoint = 'https://planetarycomputer.microsoft.com/api/data/v1';
const sentinelCache = new Map();
let satelliteContext = null;
let satelliteController = null;
let satelliteLayer = null;
let satelliteRequest = 0;
const sentinelStyle = document.createElement('style');
sentinelStyle.textContent = `
  .satellite-actions {display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
  .satellite-actions button,.satellite-view button {font:inherit;font-size:14px;background:#416b86;color:white;border:0;border-radius:6px;padding:8px 10px;cursor:pointer}
  .satellite-view {font-size:14px;color:#172b4d}
  .satellite-view p,.satellite-view label,.satellite-view a {font-size:14px;line-height:1.5;color:#172b4d;overflow-wrap:anywhere}
  .satellite-view label {display:block;margin-top:10px}
  .satellite-view select,.satellite-view input {box-sizing:border-box;max-width:100%;width:100%;font:inherit;font-size:14px;padding:7px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:#172b4d}
  .satellite-view a {display:block;margin-top:10px;color:#2563eb}
  .satellite-view [role=status] {font-size:14px;margin-top:10px;color:#172b4d}
`;
document.head.appendChild(sentinelStyle);
const sentinelToday = () => new Date().toISOString().slice(0,10);
const closeSatelliteView = () => {
  satelliteRequest++;
  if (satelliteController) satelliteController.abort();
  satelliteController=null;
  if (satelliteLayer) map.removeLayer(satelliteLayer);
  satelliteLayer=null;satelliteContext=null;basemapLayer.setOpacity(1);
};
const sentinelFetch = async (url, signal) => {
  const controller=new AbortController();
  const abort=()=>controller.abort();
  if(signal.aborted)controller.abort();else signal.addEventListener('abort',abort,{once:true});
  const timeout=setTimeout(abort,20000);
  try {
    const response=await fetch(url,{signal:controller.signal,credentials:'omit',referrerPolicy:'no-referrer'});
    if (!response.ok) throw new Error(`影像服务返回 HTTP ${response.status}`);
    return await response.json();
  } finally {clearTimeout(timeout);signal.removeEventListener('abort',abort);}
};
const sentinelContains = (geometry,lat,lon) => {
  const inside = ring => {
    let hit=false;
    for (let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const [xi,yi]=ring[i], [xj,yj]=ring[j];
      if ((yi>lat)!==(yj>lat) && lon<(xj-xi)*(lat-yi)/(yj-yi)+xi) hit=!hit;
    }
    return hit;
  };
  const polygons=geometry?.type==='Polygon'?[geometry.coordinates]:geometry?.type==='MultiPolygon'?geometry.coordinates:[];
  return polygons.some(rings=>rings.length && inside(rings[0]) && !rings.slice(1).some(inside));
};
const sentinelScene = (item,context) => {
  const properties=item.properties || {}, date=properties.datetime;
  const timestamp=Date.parse(date), end=Date.parse(context.end+'T23:59:59Z');
  const cloud=properties['eo:cloud_cover'];
  if (!item.id || item.collection!=='sentinel-2-l2a' || !Number.isFinite(timestamp) || timestamp>end ||
      timestamp>Date.now()+300000 || !item.assets?.visual || (!Array.isArray(item.bbox) || item.bbox.length!==4 || !item.bbox.every(Number.isFinite)) ||
      !sentinelContains(item.geometry,context.lat,context.lon) ||
      (context.cloud<100 && (typeof cloud!=='number' || cloud>context.cloud))) return null;
  return {id:String(item.id),date,cloud:typeof cloud==='number'?cloud:null,bbox:item.bbox,
    platform:properties.platform || 'Sentinel-2'};
};
const sentinelCloud = value => value==null?'未提供':`${Number(value).toFixed(1)}%`;
const loadSentinelScene = async (scene,context,token,status,signal) => {
  if (satelliteLayer) map.removeLayer(satelliteLayer);
  satelliteLayer=null;
  status.textContent='正在加载卫星影像';
  const params=new URLSearchParams({collection:'sentinel-2-l2a',item:scene.id,assets:'visual',asset_bidx:'visual|1,2,3',nodata:'0',format:'png'});
  const data=await sentinelFetch(`${sentinelDataEndpoint}/item/tilejson.json?${params}`,signal);
  if (token!==satelliteRequest || satelliteContext!==context || context.scene!==scene.id) return;
  // Use only the selected provider's public tile route; never arbitrary asset URLs.
  const template=data.tiles?.[0];
  if (typeof template!=='string' || !template.startsWith(sentinelDataEndpoint+'/item/tiles/')) throw new Error('影像服务未返回有效瓦片地址');
  const layer=L.tileLayer(template,{
    bounds:[[scene.bbox[1],scene.bbox[0]],[scene.bbox[3],scene.bbox[2]]],
    maxNativeZoom:14,maxZoom:18,opacity:1,
    attribution:`Contains modified Copernicus Sentinel data ${new Date(scene.date).getUTCFullYear()} · <a href="https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a" target="_blank" rel="noopener">Microsoft Planetary Computer</a>`
  });
  satelliteLayer=layer;
  let failed=false;
  layer.on('tileerror',()=>{if(token===satelliteRequest && satelliteLayer===layer){failed=true;status.textContent='部分影像瓦片加载失败，可重新查询或选择其他影像';}});
  layer.on('load',()=>{if(token===satelliteRequest && satelliteLayer===layer && !failed) status.textContent='卫星影像已显示在地图上';});
  basemapLayer.setOpacity(0);
  layer.addTo(map);
};
const querySentinel = async (context,view,results,status) => {
  const token=++satelliteRequest;
  if(satelliteController)satelliteController.abort();
  satelliteController=new AbortController();const controller=satelliteController;
  const timeout=setTimeout(()=>controller.abort(),30000);
  if (satelliteLayer) map.removeLayer(satelliteLayer);
  satelliteLayer=null;basemapLayer.setOpacity(1);results.replaceChildren();status.textContent='正在查询 Sentinel-2 影像';
  const start=new Date(context.end+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-90);
  const params=new URLSearchParams({collections:'sentinel-2-l2a',
    intersects:JSON.stringify({type:'Point',coordinates:[context.lon,context.lat]}),
    datetime:`${start.toISOString()}/${context.end}T23:59:59Z`,sortby:'-datetime',limit:'20'});
  if(context.cloud<100)params.set('query',JSON.stringify({'eo:cloud_cover':{lte:context.cloud}}));
  const url=`${sentinelEndpoint}/search?${params}`;
  try {
    let payload;
    const cached=sentinelCache.get(url);
    if(cached && Date.now()-cached.saved<300000)payload=cached.payload;
    else {
      payload=await sentinelFetch(url,controller.signal);
      if(!Array.isArray(payload.features))throw new Error('影像目录响应格式不正确');
      if(sentinelCache.size>=16)sentinelCache.delete(sentinelCache.keys().next().value);
      sentinelCache.set(url,{payload,saved:Date.now()});
    }
    if(token!==satelliteRequest || satelliteContext!==context)return;
    const scenes=[...new Map(payload.features.map(item=>sentinelScene(item,context)).filter(Boolean).map(item=>[item.id,item])).values()]
      .sort((a,b)=>Date.parse(b.date)-Date.parse(a.date) || a.id.localeCompare(b.id));
    if(!scenes.length){status.textContent='所选日期之前90天内，无符合云量条件且覆盖该位置的影像';return;}
    const label=document.createElement('label');label.textContent='可用影像（按拍摄时间排序）';results.appendChild(label);
    const select=document.createElement('select');select.setAttribute('aria-label',label.textContent);
    scenes.forEach(scene=>{const option=document.createElement('option');option.value=scene.id;option.textContent=`${scene.date.replace('T',' ').replace(/\.\d+Z$/,' UTC')} · 云量 ${sentinelCloud(scene.cloud)} · ${scene.id.split('_').find(x=>/^T\d/.test(x)) || ''}`;select.appendChild(option);});
    results.appendChild(select);
    const info=document.createElement('div');results.appendChild(info);
    const choose=async()=>{
      const scene=scenes.find(s=>s.id===select.value);context.scene=scene.id;info.replaceChildren();
      for(const text of [`拍摄时间：${scene.date.replace('T',' ').replace(/\.\d+Z$/,' UTC')}`,`整景云量：${sentinelCloud(scene.cloud)}`,'Sentinel-2 L2A 真彩色 · 原始像元10米',`影像编号：${scene.id}`]){
        const p=document.createElement('p');p.textContent=text;info.appendChild(p);
      }
      const source=document.createElement('a');source.href=`${sentinelEndpoint}/collections/sentinel-2-l2a/items/${encodeURIComponent(scene.id)}`;
      source.target='_blank';source.rel='noopener noreferrer';source.textContent='查看影像来源记录';info.appendChild(source);
      try{await loadSentinelScene(scene,context,token,status,controller.signal);}
      catch(error){if(token===satelliteRequest && context.scene===scene.id)status.textContent=error.name==='AbortError'?'影像加载超时，请重新查询':error.message;}
    };
    select.onclick=e=>e.stopPropagation();select.onchange=e=>{e.stopPropagation();choose();};
    await choose();
  } catch(error) {
    if(token===satelliteRequest)status.textContent=error.name==='AbortError'?'影像查询超时，请重新查询':error.message;
  } finally {clearTimeout(timeout);}
};
const openSatelliteView = (popup,key,coordinate,name,mode) => {
  map.fire('objectmediaopen',{kind:'satellite'});
  closeSatelliteView();
  const original=popup.getContent();
  map.setView(coordinate,key.startsWith('chokepoint:')?10:13,{animate:false});
  // An independent popup survives vessel/asset cluster rebuilds while zooming.
  popup=L.popup({popupKey:key,maxWidth:410,autoPan:false}).setLatLng(coordinate).setContent(original).openOn(map);
  const context={popup,key,lat:coordinate.lat,lon:coordinate.lng,name,mode,original,
    end:mode==='history'?(mediaSnapshotDay || sentinelToday()):sentinelToday(),cloud:100};
  satelliteContext=context;
  const content=popup.getElement()?.querySelector('.leaflet-popup-content');if(!content)return;
  content.replaceChildren();const view=document.createElement('div');view.className='satellite-view';content.appendChild(view);
  const title=document.createElement('div');title.className='field-name';title.textContent=`${name} · ${mode==='history'?'历史卫星影像':'最新卫星影像'}`;view.appendChild(title);
  const back=document.createElement('button');back.type='button';back.textContent='返回详情';
  back.onclick=e=>{e.stopPropagation();closeSatelliteView();map.closePopup(popup);focusObject(key,false);};view.appendChild(back);
  if(mediaSnapshotDay){const p=document.createElement('p');p.textContent=`对象定位日期：${mediaSnapshotDay}`;view.appendChild(p);}
  const dateLabel=document.createElement('label');dateLabel.textContent='影像查询截至日期';view.appendChild(dateLabel);
  const date=document.createElement('input');date.type='date';date.min='2015-06-23';date.max=sentinelToday();date.value=context.end;
  date.setAttribute('aria-label',dateLabel.textContent);date.onclick=e=>e.stopPropagation();view.appendChild(date);
  const cloudLabel=document.createElement('label');cloudLabel.textContent='整景云量上限';view.appendChild(cloudLabel);
  const cloud=document.createElement('select');cloud.setAttribute('aria-label',cloudLabel.textContent);
  [[100,'不限'],[60,'60%'],[30,'30%'],[10,'10%']].forEach(([n,text])=>{const option=document.createElement('option');option.value=n;option.textContent=text;cloud.appendChild(option);});
  cloud.onclick=e=>e.stopPropagation();view.appendChild(cloud);
  const actions=document.createElement('div');actions.className='satellite-actions';view.appendChild(actions);
  const submit=document.createElement('button');submit.type='button';submit.textContent='查询影像';actions.appendChild(submit);
  const status=document.createElement('div');status.setAttribute('role','status');view.appendChild(status);
  const results=document.createElement('div');view.appendChild(results);
  submit.onclick=e=>{e.stopPropagation();if(!date.value || !date.checkValidity()){status.textContent='请选择有效日期';return;}context.end=date.value;context.cloud=Number(cloud.value);querySentinel(context,view,results,status);};
  querySentinel(context,view,results,status);
};
const appendSatelliteActions = (popup,key) => {
  if(!/^(asset|port|chokepoint|vessel):/.test(key || ''))return;
  const marker=markerByPopupKey.get(key),coordinate=marker?.getLatLng?.();if(!coordinate)return;
  const content=popup.getElement()?.querySelector('.leaflet-popup-content');
  if(!content || content.querySelector('.satellite-actions'))return;
  const name=key.startsWith('vessel:')?vessels.find(v=>`vessel:${v[3]}`===key)?.[2]:[...ports,...chokepoints,...assets].find(p=>p.popupKey===key)?.name;
  const actions=document.createElement('div');actions.className='satellite-actions';
  for(const [mode,label] of [['latest','最新卫星影像'],['history','历史卫星影像']]){
    const button=document.createElement('button');button.type='button';button.textContent=label;
    button.onclick=e=>{e.stopPropagation();openSatelliteView(popup,key,coordinate,name || key,mode);};actions.appendChild(button);
  }
  content.appendChild(actions);
};
map.on('objectmediaopen',event=>{if(event.kind!=='satellite')closeSatelliteView();});
map.on('popupopen',event=>{closeSatelliteView();const key=event.popup?._source?.options?.popupKey || event.popup.options.popupKey;appendSatelliteActions(event.popup,key);});
map.on('popupclose',closeSatelliteView);
