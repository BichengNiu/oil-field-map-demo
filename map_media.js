// Public Windy players only. No API calls, credentials, or periodic collectors.
// Camera-source integration follows Ryan-Milton/Eagle-Eye; see THIRD_PARTY.md.
const mediaStyle = document.createElement('style');
mediaStyle.textContent = `
  .media-actions {display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
  .media-actions button,.media-view select {font:inherit;font-size:14px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:#172b4d;cursor:pointer;max-width:100%}
  .media-actions button {background:#8b2635;color:white;border-color:#8b2635}
  .media-view {font-size:14px;color:#172b4d}
  .media-view label {display:block;font-size:14px;margin:10px 0 6px}
  .media-view select {width:100%}
  .media-view iframe {display:block;width:100%;height:250px;border:0;margin-top:12px;background:#eef2f6}
  .media-view p {font-size:14px;line-height:1.5;color:#172b4d}
  .media-view a {font-size:14px;display:block;margin-top:10px;color:#2563eb}
`;
document.head.appendChild(mediaStyle);
const cameraPositionLayer = L.layerGroup().addTo(map);
let activeMedia = null;
const mediaSourceState = cameraCatalog.status || {};
const mediaCameras = Array.isArray(cameraCatalog.cameras) ? cameraCatalog.cameras : [];
const safePlayerUrl = value => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password &&
      ['', '443'].includes(url.port) &&
      ['webcams.windy.com','www.windy.com','windy.com','player.windy.com'].includes(url.hostname)
      ? url.href : null;
  } catch { return null; }
};
const cameraDistance = (lat, lon, camera) => {
  const rad = n => n * Math.PI / 180;
  const dLat = rad(camera.lat-lat), dLon = rad(camera.lon-lon);
  const a = Math.sin(dLat/2)**2 + Math.cos(rad(lat))*Math.cos(rad(camera.lat))*Math.sin(dLon/2)**2;
  return 6371 * 2 * Math.atan2(Math.sqrt(Math.min(1,a)), Math.sqrt(Math.max(0,1-a)));
};
const cameraMatches = (lat, lon, radius) => mediaCameras
  .filter(c => Number.isFinite(c.lat) && Number.isFinite(c.lon))
  .map(c => ({...c, distance:cameraDistance(lat,lon,c)}))
  .filter(c => c.distance <= radius)
  .sort((a,b) => a.distance-b.distance || String(a.id).localeCompare(String(b.id)));
const mediaTime = value => {
  const date = new Date(value || '');
  return Number.isFinite(date.getTime()) ? date.toISOString().replace('T',' ').replace('.000Z',' UTC') : '源站未提供';
};
const renderMedia = () => {
  const context = activeMedia;
  if (!context) return;
  cameraPositionLayer.clearLayers();
  const content = detailControl.getContainer().querySelector('.leaflet-popup-content');
  if (!content) return;
  // Removing the old iframe stops video/audio when switching objects or modes.
  content.replaceChildren();
  const view = document.createElement('div');view.className='media-view';content.appendChild(view);
  const title = document.createElement('div');title.className='field-name';title.textContent=context.name;view.appendChild(title);
  const actions = document.createElement('div');actions.className='media-actions';view.appendChild(actions);
  const addButton = (label, handler) => {const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=event=>{event.stopPropagation();handler();};actions.appendChild(b);};
  addButton('返回详情', () => {const old=activeMedia;activeMedia=null;cameraPositionLayer.clearLayers();old.popup.setContent(old.original);map.fire('popupopen',{popup:old.popup});});
  addButton('实时画面', () => {context.mode='live';renderMedia();});
  addButton('回看', () => {context.mode='replay';renderMedia();});
  const row = text => {const p=document.createElement('p');p.textContent=text;view.appendChild(p);return p;};
  const select = (label, options, value, handler) => {
    const l=document.createElement('label');l.textContent=label;view.appendChild(l);
    const s=document.createElement('select');s.setAttribute('aria-label',label);
    options.forEach(([v,t]) => {const o=document.createElement('option');o.value=v;o.textContent=t;s.appendChild(o);});
    s.value=value;s.onclick=event=>event.stopPropagation();s.onchange=event=>{event.stopPropagation();handler(s.value);};view.appendChild(s);return s;
  };
  if (mediaSnapshotDay) row(`对象定位日期：${mediaSnapshotDay}；画面时间以播放器为准`);
  select('附近摄像头范围', [20,50,100,250].map(n=>[String(n),`${n} 公里`]), String(context.radius), value=>{context.radius=Number(value);context.cameraId=null;renderMedia();});
  const matches = cameraMatches(context.lat,context.lon,context.radius);
  if (mediaSourceState.status === 'not_configured') row('画面来源未配置');
  else if (mediaSourceState.status === 'error') row('画面来源更新失败，保留上次摄像头目录');
  if (mediaSourceState.completed_at) row(`摄像头目录更新：${mediaTime(mediaSourceState.completed_at)}`);
  if (!matches.length) {row(`附近 ${context.radius} 公里内暂无可用摄像头`);return;}
  if (!matches.some(c=>c.id===context.cameraId)) context.cameraId=matches[0].id;
  select('附近摄像头', matches.map(c=>[c.id,`${c.title} · ${c.distance.toFixed(1)} 公里`]), context.cameraId, value=>{context.cameraId=value;renderMedia();});
  const camera=matches.find(c=>c.id===context.cameraId);
  row(`摄像头画面更新：${mediaTime(camera.updated_at)}`);
  row(`摄像头位置：${camera.lat.toFixed(5)}, ${camera.lon.toFixed(5)}`);
  L.circleMarker([camera.lat,camera.lon],{radius:7,color:'#0e7490',fillOpacity:.8})
    .bindTooltip(escapeHTML(`附近摄像头 · ${camera.title}`)).addTo(cameraPositionLayer);
  const players=camera.players || {};
  let src;
  if (context.mode==='live') {
    src=safePlayerUrl(players.live);
    if (!src) row('该摄像头不提供实时直播，可选择回看');
  } else {
    const periods=[['day','过去24小时'],['month','过去一个月'],['year','过去一年'],['lifetime','全部历史']].filter(([key])=>safePlayerUrl(players[key]));
    if (!periods.length) row('该摄像头未提供回看');
    else {
      if (!periods.some(([key])=>key===context.period)) context.period=periods[0][0];
      select('延时回看',periods,context.period,value=>{context.period=value;renderMedia();});
      src=safePlayerUrl(players[context.period]);
    }
  }
  if (src) {
    const frame=document.createElement('iframe');frame.src=src;frame.title=context.mode==='live'?'摄像头实时直播':'摄像头延时回看';
    frame.allow='autoplay; fullscreen; picture-in-picture';frame.allowFullscreen=true;
    frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups');
    frame.referrerPolicy='strict-origin-when-cross-origin';actions.insertAdjacentElement('afterend',frame);
  }
  const source=document.createElement('a');source.href=`https://www.windy.com/webcams/${encodeURIComponent(camera.id)}`;
  source.target='_blank';source.rel='noopener noreferrer';source.textContent='在 Windy 查看摄像头与画面时间';view.appendChild(source);
};
const appendMediaActions = (popup, key) => {
  if (!/^(port|chokepoint|vessel):/.test(key || '')) return;
  const marker=markerByPopupKey.get(key);
  const coordinate=marker?.getLatLng?.();
  if (!coordinate) return;
  const content=popup.getElement()?.querySelector('.leaflet-popup-content');
  if (!content || content.querySelector('.media-actions')) return;
  const original=popup.getContent();
  const name=key.startsWith('vessel:') ? vessels.find(v=>`vessel:${v[3]}`===key)?.[2]
    : [...ports,...chokepoints].find(p=>p.popupKey===key)?.name;
  const actions=document.createElement('div');actions.className='media-actions';
  for (const [mode,label] of [['live','实时画面'],['replay','回看']]) {
    const button=document.createElement('button');button.type='button';button.textContent=label;
    button.onclick=event=>{event.stopPropagation();map.fire('objectmediaopen',{kind:'camera'});activeMedia={key,popup,original,name:name || key,lat:coordinate.lat,lon:coordinate.lng,mode,radius:50,period:'day',cameraId:null};renderMedia();};
    actions.appendChild(button);
  }
  content.appendChild(actions);
};
map.on('popupopen', event => {
  activeMedia=null;cameraPositionLayer.clearLayers();
  const key=event.popup?._source?.options?.popupKey || event.popup.options.popupKey;
  appendMediaActions(event.popup,key);
});
map.on('popupclose', () => {
  // A detached public player must not keep streaming in the background.
  detailControl.getContainer().querySelectorAll('iframe').forEach(frame=>frame.remove());
  activeMedia=null;cameraPositionLayer.clearLayers();
});

map.on('objectmediaopen',event=>{if(event.kind!=='camera'){activeMedia=null;cameraPositionLayer.clearLayers();detailControl.getContainer().querySelectorAll('iframe').forEach(frame=>frame.remove());}});
