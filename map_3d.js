/* Cesium is loaded only when the user selects the 3D view. */
(async () => {
  const status = document.getElementById('status');
  if (!window.Cesium) return;
  const C = window.Cesium;
  const escape = value => String(value ?? '—').replace(/[&<>"']/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[c]));
  const color = value => C.Color.fromCssColorString(value);
  try {
    await installCesiumFrameWorkers(C);
    // Never use the SDK's bundled demo ion token.
    C.Ion.defaultAccessToken = '';
    const viewer = new C.Viewer('globe', {
      baseLayer: false, baseLayerPicker: false, geocoder: false,
      animation: false, timeline: false, sceneModePicker: false,
      homeButton: false, navigationHelpButton: false, fullscreenButton: false,
      infoBox: false, selectionIndicator: true, targetFrameRate:30,
      contextOptions: {webgl: {preserveDrawingBuffer: true}}
    });
    document.addEventListener('visibilitychange', () => {
      viewer.useDefaultRenderLoop = !document.hidden;
    });
    viewer.scene.globe.depthTestAgainstTerrain = false;
    viewer.scene.renderError.addEventListener(() => {
      status.textContent = '三维绘制失败，请检查浏览器 WebGL 或切回二维视图。';
    });
    const imagery = new C.UrlTemplateImageryProvider({
      url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      maximumLevel:19,
      credit:new C.Credit('影像：Esri, Maxar, Earthstar Geographics, GIS User Community',true)
    });
    viewer.imageryLayers.addImageryProvider(imagery);
    document.getElementById('legend').innerHTML = payload.legend;
    document.getElementById('dates').textContent = payload.dates;
    const detail = document.getElementById('detail');
    let track = null;
    document.getElementById('close').onclick = () => {
      detail.style.display = 'none'; viewer.selectedEntity = undefined;
      if (track) viewer.entities.remove(track);
      track = null;
    };
    const entityByKey = new Map();
    const records = new Map();
    function icon(shape, fill, outline, angle = 0) {
      const paths = {asset:'M12 2L22 12L12 22L2 12Z', port:'M4 4H20V20H4Z',
        choke:'M6 3H18L24 12L18 21H6L0 12Z', vessel:'M12 2L21 22L12 17L3 22Z'};
      return 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="-2 -2 28 28"><path d="${paths[shape]}" transform="rotate(${angle} 12 12)" fill="${fill}" stroke="${outline}" stroke-width="2"/></svg>`);
    }
    function addPoint(row, shape, fill, outline = '#ffffff', angle = 0) {
      if (!Number.isFinite(Number(row.lon)) || !Number.isFinite(Number(row.lat))) return;
      const entity = viewer.entities.add({id:row.popupKey, name:row.name,
        position:C.Cartesian3.fromDegrees(Number(row.lon), Number(row.lat)),
        billboard:{image:icon(shape, fill, outline, angle), width:24, height:24,
          heightReference:C.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance:Infinity}});
      entityByKey.set(row.popupKey, entity); records.set(entity.id, {...row, color:fill});
    }
    payload.assets.forEach(row => addPoint(row, 'asset', '#808080'));
    payload.ports.forEach(row => addPoint(row, 'port', '#2563eb'));
    payload.chokepoints.forEach(row => addPoint(row, 'choke', '#7c3aed'));
    payload.vessels.forEach(v => {
      const palette = v[19] ? {tanker:'#ef4444',cargo:'#2563eb',other:'#64748b'}
        : {tanker:'#fca5a5',cargo:'#a5b4fc',other:'#cbd5e1'};
      const fill = palette[v[17]] || palette.other;
      const values = [['船型',v[5]],['船籍',v[18]],['MMSI',v[3]],['航速（节）',v[7]],
        ['航行状态',v[9]],['目的地',v[11]],['观测时间',v[12]],['数据源',v[14]]];
      addPoint({lat:v[0],lon:v[1],name:v[2],popupKey:`vessel:${v[3]}`,mmsi:String(v[3]),
        popup:`<div class="field-name">${escape(v[2])}</div>` + values.map(([label,value]) =>
          `<div class="row"><span>${label}</span><strong>${escape(value)}</strong></div>`).join('')},
        'vessel',fill,v[19] ? '#dc2626' : '#ffffff',Number(v[8]) || 0);
    });
    for (const feature of payload.pipelines.features || []) {
      const p = feature.properties;
      if (p.map_drawable === false) continue;
      const geometry = feature.geometry;
      const lines = geometry?.type === 'LineString' ? [geometry.coordinates]
        : geometry?.type === 'MultiLineString' ? geometry.coordinates : [];
      const fill = p.fuel === 'Gas' ? '#416b86' : '#8b2635';
      const key = `pipeline:${p.project_id}`;
      lines.forEach((line, i) => {
        if (line.length < 2) return;
        const entity = viewer.entities.add({id:`${key}:${i}`,name:p.name,polyline:{
          positions:C.Cartesian3.fromDegreesArray(line.flatMap(pt => [pt[0],pt[1]])),
          width:3,clampToGround:true,
          material:p.status === 'operating' ? color(fill)
            : new C.PolylineDashMaterialProperty({color:color(fill),dashLength:16})}});
        const record = {popupKey:key,popup:p.popup};
        records.set(entity.id,record);
        // One searchable target encloses all segments of the same project.
        const project = entityByKey.get(key) || [];
        project.push(entity); entityByKey.set(key,project);
      });
    }
    function show(entity) {
      const record = records.get(entity?.id);
      if (!record) return;
      document.getElementById('content').innerHTML = record.popup;
      detail.style.top = `${document.getElementById('legend').offsetHeight + 24}px`;
      detail.style.display = 'block';
      if (track) viewer.entities.remove(track);
      track = null;
      const points = payload.tracks[record.mmsi] || [];
      if (points.length > 1) track = viewer.entities.add({polyline:{
        positions:C.Cartesian3.fromDegreesArray(points.flatMap(p => [p[1],p[0]])),
        width:3, clampToGround:true,
        material:new C.PolylineDashMaterialProperty({color:color(record.color),dashLength:12})}});
      viewer.scene.requestRender();
    }
    viewer.selectedEntityChanged.addEventListener(show);
    viewer.camera.setView({destination:C.Cartesian3.fromDegrees(49,25,4500000),
      orientation:{heading:0,pitch:C.Math.toRadians(-65),roll:0}});
    // Retain the camera across layer changes and snapshot selection.
    try {
      const saved = JSON.parse(sessionStorage.getItem('energy-map-3d-view'));
      if (saved && ['x','y','z','heading','pitch','roll'].every(k => Number.isFinite(saved[k])))
        viewer.camera.setView({destination:new C.Cartesian3(saved.x,saved.y,saved.z),orientation:saved});
    } catch (_) { /* Browser storage can be disabled. */ }
    viewer.camera.moveEnd.addEventListener(() => {
      const camera = viewer.camera;
      try { sessionStorage.setItem('energy-map-3d-view',JSON.stringify({
        x:camera.positionWC.x,y:camera.positionWC.y,z:camera.positionWC.z,
        heading:camera.heading,pitch:camera.pitch,roll:camera.roll})); } catch (_) {}
    });
    async function focus() {
      const target = entityByKey.get(payload.focus.key);
      if (!target) return;
      const token = `${payload.focus.revision}:${payload.focus.key}`;
      try {
        if (sessionStorage.getItem('energy-map-3d-focus') === token) return;
      } catch (_) {}
      const entities = Array.isArray(target) ? target : [target];
      const points = entities.flatMap(entity => entity.polyline
        ? entity.polyline.positions.getValue(viewer.clock.currentTime)
        : [entity.position.getValue(viewer.clock.currentTime)]);
      viewer.camera.flyToBoundingSphere(C.BoundingSphere.fromPoints(points),{
        duration:0,offset:new C.HeadingPitchRange(0,C.Math.toRadians(-45),
          Math.max(15000,C.BoundingSphere.fromPoints(points).radius * 3))});
      viewer.selectedEntity = entities[0];
      try { sessionStorage.setItem('energy-map-3d-focus',token); } catch (_) {}
    }
    // Slow providers must not leave the selected view waiting indefinitely.
    async function limited(promise) {
      let timer;
      try {
        return await Promise.race([promise,new Promise((_,reject) => {
          timer = setTimeout(() => reject(new Error('Map source timeout')),20000);
        })]);
      } finally { clearTimeout(timer); }
    }
    let photoreal = false;
    const failures = [];
    if (payload.google_key) {
      try {
        const tiles = await limited(C.createGooglePhotorealistic3DTileset({key:payload.google_key}));
        viewer.scene.primitives.add(tiles); photoreal = true;
      } catch (_) { failures.push('Google 三维实景加载失败'); }
    }
    if (!photoreal && payload.ion_token) {
      try {
        const resource = await limited(C.IonResource.fromAssetId(2275207,{accessToken:payload.ion_token}));
        const tiles = await limited(C.Cesium3DTileset.fromUrl(resource));
        viewer.scene.primitives.add(tiles); photoreal = true;
      } catch (_) { failures.push('Cesium ion 三维实景加载失败'); }
    }
    if (photoreal) {
      viewer.scene.globe.show = false;
      document.getElementById('legend').insertAdjacentHTML('afterbegin','<div>Google 三维实景（历史影像）</div>');
      status.textContent = '';
    } else {
      document.getElementById('legend').insertAdjacentHTML('afterbegin','<div>卫星地形（历史影像）</div>');
      try {
        const terrain = payload.ion_token
          ? await limited(C.IonResource.fromAssetId(1,{accessToken:payload.ion_token}))
          : 'https://terrain.reearth.land/cesium-mesh/ellipsoid';
        viewer.terrainProvider = await limited(C.CesiumTerrainProvider.fromUrl(terrain));
        let terrainErrors = 0;
        viewer.terrainProvider.errorEvent.addEventListener(() => {
          if (++terrainErrors < 3) return;
          viewer.terrainProvider = new C.EllipsoidTerrainProvider();
          status.textContent = '地形瓦片不可用，已显示卫星地球。';
          viewer.scene.requestRender();
        });
        if (!payload.ion_token) viewer.scene.frameState.creditDisplay.addStaticCredit(
          new C.Credit('地形：Re:Earth / Mapterhorn · CC BY 4.0',true));
        status.textContent = failures.length ? failures.join('；') + '，已显示卫星地形。' : '';
      } catch (_) {
        status.textContent = '三维地形加载失败，已显示卫星地球。';
      }
    }
    await focus();
    if (payload.screenshot) {
      viewer.render();
      const a = document.createElement('a');
      a.download = '能源监测三维地图.png'; a.href = viewer.canvas.toDataURL('image/png'); a.click();
    }
    viewer.scene.requestRender();
    // Read-only diagnostics for browser verification.
    window.energy3d = {viewer, entityByKey, records, photoreal};
  } catch (_) {
    status.textContent = '三维地图加载失败，请检查浏览器 WebGL 和网络后重试。';
  }
})();
